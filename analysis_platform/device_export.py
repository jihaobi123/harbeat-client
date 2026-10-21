"""Export source-bound local-execution sidecars; never change source reports.

python -m analysis_platform.device_export --library /path/current --output /nas/device-v1 --profiles-only
Repeat with --track-id ID to materialize reusable 16-second stem chunks.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
import time

import numpy as np
import scipy
import soundfile as sf
from scipy.signal import resample_poly

from .execution_profiles import VERSION, stem_profile, groove_profile, bar_evidence
from . import execution_profiles
from metric_mix.prepare import source_assets, sha

STEMS = ('drums','bass','other','vocals')
EXCLUDED = {'track-080bca25199811cdd57d': 'published report fingerprint differs from current NAS report; rebind required'}


def algorithm_sha():
    return hashlib.sha256(Path(execution_profiles.__file__).read_bytes()).hexdigest()


def json_bytes(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()


def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.part-'+str(os.getpid()))
    temp.write_bytes(json_bytes(value));os.replace(temp,path)


def immutable(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=data:raise ValueError('immutable sidecar already exists with different bytes')
    else:
        temp=path.with_name(path.name+'.part-'+str(os.getpid()));temp.write_bytes(data);os.replace(temp,path)


def export_track(track,nas,reports,output,*,profiles_only=False,chunk_seconds=16):
    if not re.fullmatch(r'[a-f0-9]{64}',str(track.get('reportId',''))):raise ValueError('invalid report identifier')
    if track['id'] in EXCLUDED:raise ValueError(EXCLUDED[track['id']])
    paths,proof=source_assets(track,nas,reports)
    if any(key not in paths for key in STEMS):raise ValueError('all four stems required')
    info={k:sf.info(paths[k]) for k in STEMS}
    sr=info['drums'].samplerate;frames=info['drums'].frames
    if any(v.samplerate!=sr or v.frames!=frames or v.channels!=2 for v in info.values()):
        raise ValueError('stem sample rate, channel count and sample lengths must match')
    master=sf.info(paths['master'])
    if master.frames*sr!=frames*master.samplerate:
        raise ValueError('master and stems must have identical sample durations for device execution')
    binding={'trackId':track['id'],'sourceSha256':proof['assets']['master']['sha256'],
             'reportSha256':proof['reportSha256'],'manifestSha256':proof['manifestSha256'],'runId':proof['runId']}
    profile={'schema':VERSION,**binding,'sourceTimeOrigin':'master_audio_start','frameSeconds':.125,
             'algorithmSha256':algorithm_sha(),
             'software':{'numpy':np.__version__,'scipy':scipy.__version__,'soundfile':sf.__version__},
             'stems':{},'rhythm':bar_evidence(track),
             'limitations':['RMS activity is not speech VAD; existing vocal rules remain authoritative.',
                            'Band onsets are not kick/snare labels; STFT chroma is not chord/key truth.',
                            '8/16-bar completeness does not certify musical phrase boundaries.',
                            'BeatThis/All-In-One upstream adapters remain optional; model agreement is unknown here.']}
    beats=sorted(set(float(x) for bar in (track.get('alignment') or {}).get('bars',[]) if bar.get('valid') for x in bar.get('beats',[])))
    device={'schema':'harbeat.execution-track.v1',**binding,'sampleRate':sr,'channels':2,
            'duration':frames/sr,'frames':frames,'sourceTimeOrigin':'master_audio_start','stems':{},
            'masterSampleGrid':{'sampleRate':master.samplerate,'frames':master.frames,
                                'mapping':'same origin and exact rational duration; decode into shared device audio sample rate'}}
    for key in STEMS:
        rows=[];events=[];segments=[]
        with sf.SoundFile(paths[key]) as source:
            for start_frame in range(0,frames,round(chunk_seconds*sr)):
                count=min(round(chunk_seconds*sr),frames-start_frame)
                data=source.read(count,dtype='float32',always_2d=True)
                if len(data)!=count:raise ValueError('short stem read')
                start=start_frame/sr;end=(start_frame+count)/sr
                # Analyze independent chunks at 16 kHz; file export remains original source rate.
                mono=data.mean(axis=1);divisor=__import__('math').gcd(sr,16000)
                low=resample_poly(mono,16000//divisor,sr//divisor)
                result=stem_profile(low,16000,start=start,harmony=key in ('bass','other'))
                rows.extend(result['frames'])
                if key=='drums':events.extend(groove_profile(low,16000,beats,start=start)['events'])
                if profiles_only:continue
                if float(np.max(abs(data)))>1:
                    raise ValueError('source exceeds PCM_24 range; lossless float asset required')
                dest=output/'objects';dest.mkdir(parents=True,exist_ok=True)
                fd,temp=tempfile.mkstemp(prefix='.segment-',suffix='.flac',dir=dest);os.close(fd)
                try:
                    # FLOAT source quantization is explicit and bounded to 24-bit lossless PCM.
                    sf.write(temp,data,sr,format='FLAC',subtype='PCM_24')
                    checksum=sha(temp);target=dest/(checksum+'.flac')
                    if target.exists() and target.stat().st_size==Path(temp).stat().st_size and sha(target)==checksum:os.unlink(temp)
                    else:os.replace(temp,target)
                finally:
                    if os.path.exists(temp):os.unlink(temp)
                segments.append({'start':start,'end':end,'startFrame':start_frame,'endFrame':start_frame+count,
                                 'asset':{'url':'/listen/execution-media/'+checksum+'.flac','sha256':checksum,
                                          'duration':count/sr,'bytes':target.stat().st_size,'sampleRate':sr,
                                          'channels':2,'frames':count,'encoding':'FLAC PCM_24'}})
        profile['stems'][key]={'sourceSha256':proof['assets'][key]['sha256'],'frames':rows,
                               'frameSeconds':.125,'activityBasis':result['activityBasis'],
                               'harmonyBasis':result['harmonyBasis'] if key in ('bass','other') else None}
        if key=='drums':profile['groove']={'status':'ready' if events else 'unknown','events':events,
                                          'basis':'multiband positive STFT flux at 10 ms; phase measured against observed beats'}
        device['stems'][key]={'sourceSha256':proof['assets'][key]['sha256'],'segments':segments}
    raw=json_bytes(profile);checksum=hashlib.sha256(raw).hexdigest();profile_path=output/'profiles'/(checksum+'.json')
    immutable(profile_path,raw)
    device['profile']={'sha256':checksum,'url':'/listen/execution/profiles/'+checksum+'.json','bytes':len(raw)}
    if not profiles_only:atomic_json(output/'tracks'/(track['id']+'.json'),device)
    return {'trackId':track['id'],**binding,'profile':device['profile'],'stemSha256':{k:proof['assets'][k]['sha256'] for k in STEMS},'assetsReady':not profiles_only,
            'trackUrl':'/listen/execution/tracks/'+track['id']+'.json' if not profiles_only else None,
            'bytes':sum(s['asset']['bytes'] for stem in device['stems'].values() for s in stem['segments'])}


def export_row(args,row,out):
    # Reload under a per-track lock: a reservation can enter between background
    # tracks without waiting for the entire catalog, and no index updates vanish.
    import fcntl
    with (out/'.export.lock').open('a') as export_lock:
        fcntl.flock(export_lock.fileno(),fcntl.LOCK_EX)
        old=json.loads((out/'index.json').read_text()) if (out/'index.json').exists() else {}
        rows={x['trackId']:x for x in old.get('tracks',[])};failed={x['trackId']:x for x in old.get('excluded',[])}
        try:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',row['id']):raise ValueError('invalid track identifier')
            detail=(args.library/row['detailUrl']).resolve()
            if args.library.resolve() not in detail.parents:raise ValueError('unsafe catalog path')
            track=json.loads(detail.read_text())['track']
            if track['id']!=row['id']:raise ValueError('catalog detail identity mismatch')
            if args.incremental:
                previous=rows.get(track['id'],{})
                provenance=track.get('provenance') or {}
                matches=all(previous.get(k)==provenance.get(v) for k,v in [('runId','runId'),('sourceSha256','masterSha256'),('reportSha256','reportSha256')])
                profile_id=(previous.get('profile') or {}).get('sha256','')
                profile_file=out/'profiles'/(profile_id+'.json')
                cached=json.loads(profile_file.read_text()) if re.fullmatch(r'[a-f0-9]{64}',profile_id) and profile_file.is_file() and sha(profile_file)==profile_id else {}
                if matches and cached.get('schema')==VERSION and cached.get('algorithmSha256')==algorithm_sha() and (args.profiles_only or previous.get('assetsReady')):
                    print(json.dumps({'trackId':track['id'],'status':'cached'}),flush=True)
                    return
            entry=export_track(track,args.nas,args.reports,out,profiles_only=args.profiles_only)
            # A profile-only rerun must not hide already exported current audio assets.
            previous=rows.get(track['id'],{})
            same=all(previous.get(k)==entry.get(k) for k in ['trackId','sourceSha256','reportSha256','manifestSha256','runId','stemSha256','profile'])
            if args.profiles_only and previous.get('assetsReady') and same:
                entry.update(assetsReady=True,trackUrl=rows[track['id']]['trackUrl'],bytes=rows[track['id']]['bytes'])
            rows[track['id']]=entry
            failed.pop(track['id'],None)
            print(json.dumps({'trackId':track['id'],'status':'ready','bytes':entry['bytes']}),flush=True)
        except Exception as exc:
            rows.pop(row['id'],None)
            if re.fullmatch(r'[A-Za-z0-9_-]{1,160}',row['id']):
                (out/'tracks'/(row['id']+'.json')).unlink(missing_ok=True)
            failed[row['id']]={'trackId':row['id'],'reason':str(exc)}
            print(json.dumps({'trackId':row['id'],'status':'excluded','reason':str(exc)}),flush=True)
        atomic_json(out/'index.json',{'schema':'harbeat.execution-library.v1','generatedAt':int(time.time()),
                                     'tracks':list(rows.values()),'excluded':list(failed.values()),'profileSchema':VERSION})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--nas',type=Path,default=Path('/mnt/nas/harbeat/preprocess'))
    parser.add_argument('--reports',type=Path,default=Path('/mnt/nas/harbeat/data/analysis-platform/reports'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--track-id',action='append',default=[])
    parser.add_argument('--profiles-only',action='store_true')
    parser.add_argument('--incremental',action='store_true',help='Reuse source-bound profiles already hash-verified in this export')
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    index=json.loads((args.library/'library.json').read_text())
    for row in index['tracks']:
        if args.track_id and row['id'] not in args.track_id:continue
        export_row(args,row,out)


if __name__=='__main__':main()
