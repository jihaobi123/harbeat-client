#!/usr/bin/env python3
"""Build additive mix profiles from original reports; optionally run exact-interval genre.
Run from the repository root: python -m scripts.build_mix_profiles --help
"""
import argparse, hashlib, json, os
from pathlib import Path
from analysis_platform.mix_profiles import build_profiles, requested_intervals, VERSION

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False));tmp.replace(path)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--catalog',type=Path,required=True);ap.add_argument('--reports',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--sidecars',type=Path,required=True);ap.add_argument('--audio-root',type=Path);ap.add_argument('--models-dir');ap.add_argument('--embedding-cache-dir');ap.add_argument('--infer',action='store_true')
    args=ap.parse_args(); catalog=json.loads(args.catalog.read_text());audit=[]
    for track in catalog['tracks']:
        rp=args.reports/(track['reportId']+'.json'); report=json.loads(rp.read_text()); local=None
        intervals=requested_intervals(track)
        identity={'schema':VERSION,'masterSha256':track['provenance']['masterSha256'],'intervals':intervals}
        key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        side=args.sidecars/(track['id']+'-'+key[:16]+'.json')
        if side.exists():
            cached=json.loads(side.read_text())
            if cached.get('identity')!=identity:raise ValueError('invalid sidecar identity')
            local=cached['genre']
        if args.infer:
            if not args.audio_root or not args.models_dir:raise ValueError('--infer requires --audio-root and --models-dir')
            root=args.audio_root.resolve(); audio=(root/report['documents']['core']['assets']['master']['storage_key']).resolve()
            if not audio.is_relative_to(root):raise ValueError('audio outside root')
            if sha(audio)!=identity['masterSha256']:raise ValueError('audio content SHA mismatch')
            model_files={name:sha(Path(args.models_dir)/name) for name in ['discogs-effnet-bs64-1.pb','genre_discogs400-discogs-effnet-1.pb','genre_discogs400-discogs-effnet-1.json']}
            recorded=(local or {}).get('data',{}).get('model_files',{})
            if local is None or local.get('status')!='ready' or any(recorded.get(k)!=v for k,v in model_files.items()):
                from analysis_platform.model_worker import predict
                local=predict('genre',{'audio':str(audio),'config':{'models_dir':args.models_dir,'embedding_cache_dir':args.embedding_cache_dir,'genre_intervals':intervals}})
                save(side,{'identity':identity,'genre':local})
            if local.get('status')!='ready':raise RuntimeError(str(local))
        profile=build_profiles(report,track,local)
        profile['source']['reportFileSha256']=sha(rp)
        if local:profile['source']['genreSidecarSha256']=sha(side)
        track['mixProfile']=profile
        track['warnings']=[x for x in track.get('warnings',[]) if x!='能量使用已有局部曲线作启发式比较，未作跨曲感知校准']+['新能量规则使用统一 dBFS 功率；不是跨曲感知能量模型']
        audit.append({'track':track['title'],'sections':len(profile['sections']),'windows':len(profile['windows']),
                      'directStyleCandidates':sum(w['takeover']['style']['status']=='model_candidate' for w in profile['windows']),
                      'measuredEnergyFrames':sum(x['status']=='measured' for x in profile['energyCurve']),
                      'source':profile['source']})
        print(json.dumps({k:v for k,v in audit[-1].items() if k!='source'},ensure_ascii=False),flush=True)
    catalog['version']='V3 Live Preview 0.2 — joint local intents'
    catalog['mixProfileSchema']=VERSION
    catalog['limitations']=[x for x in catalog.get('limitations',[]) if '风格筛选为模型 Trap/Grime' not in x]
    catalog['limitations']+=['局部风格为实验模型候选；弱证据保留待确认','能量统一为 dBFS RMS，比较 A 交接前4秒和 B 接管后连续4组4秒；不代表已标定的听感能量']
    save(args.output,catalog);save(args.output.with_name('profile-audit.json'),audit)
if __name__=='__main__':main()
