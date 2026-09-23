#!/usr/bin/env python3
"""Automatic acoustic candidates; never creates human reviews."""
import argparse,copy,hashlib,json,subprocess
from pathlib import Path


def quiet_ranges(points,threshold=-32):
    out=[]
    for p in points:
        v=p['rms_dbfs'] if p['rms_dbfs'] is not None else -120.
        if v>threshold:continue
        if out and abs(out[-1]['end']-p['start'])<.00001:out[-1]['end']=p['end'];out[-1]['max']=max(out[-1]['max'],v)
        else:out.append({'start':p['start'],'end':p['end'],'max':v})
    return [g for g in out if g['end']-g['start']>=.199]


def candidates(t,signals):
    assert signals['audio_sha256']==t['provenance']['masterSha256']
    v=signals['vocals'];assert v['source']=='separated_vocal_rms_hysteresis_v1';assert v['coverage_sec']>=t['duration']-.05
    source=v['asset']['verified_sha256'];assert source==v['asset']['declared_sha256']
    gaps=quiet_ranges(v['points']);exits=[];windows={}
    def proof(g):return {'method':'vocal_gap_v1','masterSha256':signals['audio_sha256'],'vocalSha256':source,'reportId':t['reportId'],'quietStart':g['start'],'quietEnd':g['end'],'maxRmsDbfs':g['max'],'thresholdDbfs':-32,'frameSec':v['parameters']['frame_sec']}
    for si,s in enumerate(t['sections'][:-1]):
        for bar in t['bars']:
            if not s['end']<=bar<=s['end']+min(4,480/t['bpm']):continue
            for g in gaps:
                cut=max(g['start']+.05,min(g['end']-.05,bar))
                if abs(cut-bar)>.065 or not s['end']<=cut<=s['end']+min(4,480/t['bpm']) or cut>=t['duration']-.1:continue
                if g['start']+.05<=cut<=g['end']-.05:exits.append({'id':f'auto-{si}-{bar:.3f}','cut':cut,'rawBar':bar,'sectionEnd':s['end'],'start':s['start'],'label':s['label'],'acoustic':proof(g)})
    for si,s in enumerate(t['sections']):
        for i,start in enumerate(t['bars']):
            for n in [1,2,4]:
                if i+n>=len(t['bars']):continue
                end=t['bars'][i+n]
                if start<s['start'] or end>s['end'] or end+12>t['duration']:continue
                # Incoming original material must also be outside existing VAD, including a 100ms takeover margin.
                if t['vocals'] is None or any(hi>start and lo<end+.1 for lo,hi in t['vocals']):continue
                g=next((g for g in gaps if g['start']<=start and g['end']>=end+.1),None)
                if g:windows[f'auto-{si}-{i}-{n}']={'start':start,'end':end,'bars':n,'sectionStart':s['start'],'sectionEnd':s['end'],'lane':'original_silent','sourceHashes':[signals['audio_sha256']],'gridSource':'existing_or_intro_candidate','acoustic':proof(g),'role':s['label']}
    return {'exits':exits,'windows':windows,'diagnostics':{'quietGaps':gaps,'modelSectionEnds':[s['end'] for s in t['sections']],'status':'acoustic_candidates_not_human_verified','vocalSha256':source}}


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('input',type=Path);ap.add_argument('output',type=Path);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();d=json.loads(a.input.read_text());tracks=d['catalog']['tracks'];out={'schema':'harbeat.protected.auto.v1','policy':'acoustic-v1','tracks':tracks,'evidence':{},'reviews':{},'limitations':['Automatic acoustic candidate, not verified lyrical sentence or section semantics.','One/two/four-bar original silent entries; no manual-review bypass of the acoustic checks.','No 18 second forced cut; no fallback to normal V3.']};media=a.output/'media';media.mkdir(parents=True,exist_ok=True)
    for t in tracks:
        ev=candidates(t,d['signals'][t['id']]);out['evidence'][t['id']]=ev
        # Use the frozen, already-public decoded native clip, keeping its exact time origin.
        native=(a.root/t['native']['url'].removeprefix('/analysis-lab-static/')).resolve();assert native.is_relative_to(a.root.resolve());assert sha(native)==t['native']['sha256'];windows=[]
        for wid,e in ev['windows'].items():
            w={k:e[k] for k in ['start','end','bars','role']};w.update(id=wid,energy=0,variants={})
            for target in tracks:
                if target['id']==t['id']:continue
                duration=w['bars']*240/target['bpm'];rate=(w['end']-w['start'])/duration
                if not .8<=rate<=1.2:continue
                dest=media/f'{t["id"]}-{wid}-{target["id"][6:]}.flac';filt=f'atrim=start={w["start"]:.9f}:end={w["end"]:.9f},asetpts=PTS-STARTPTS,atempo={rate:.9f},apad=whole_dur={duration:.9f},atrim=end={duration:.9f}'
                subprocess.run(['ffmpeg','-y','-nostdin','-v','error','-i',str(native),'-af',filt,'-ar','44100','-ac','2','-c:a','flac','-sample_fmt','s16',str(dest)],check=True)
                actual=float(json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(dest)]))['format']['duration']);assert abs(actual-duration)<1/44100
                w['variants'][target['id']]={'url':'media/'+dest.name,'sha256':sha(dest),'duration':actual,'bytes':dest.stat().st_size,'rate':rate,'recipe':filt,'sourceNativeSha256':t['native']['sha256']}
            if w['variants']:windows.append(w)
        t['windows']=windows;print(t['title'],'exits',len(ev['exits']),'entries',len(windows),flush=True)
    (a.output/'auto-catalog.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print('DONE',sum(len(w['variants']) for t in tracks for w in t['windows']),flush=True)
if __name__=='__main__':main()
