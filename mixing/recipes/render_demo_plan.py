#!/usr/bin/env python3
"""Build an explicit local audition from six hash-matched source snapshots."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from analysis_platform.demo_preview import candidate
from analysis_platform.demo_render import render
from analysis_platform.dj_plan import plan
from analysis_platform.report import digest,validate_report


def main():
    p=argparse.ArgumentParser();p.add_argument('--inventory',type=Path,required=True);p.add_argument('--reports',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--audio-dir',type=Path,help='Resolve inventory filenames within this audio folder');p.add_argument('--preview',action='store_true');p.add_argument('--plan-only',action='store_true');args=p.parse_args()
    if not args.preview:raise SystemExit('This candidate-grid audition requires --preview')
    files=json.loads(args.inventory.read_text())['files'];contracts=[];tracks=[]
    for f in files:
        report=validate_report(json.loads((args.reports/(f['sha256']+'.json')).read_text()))
        if report['audio'].get('sha256')!=f['sha256']:raise ValueError('source report identity mismatch')
        c=candidate(report);contracts.append(c)
        audio_path=str(args.audio_dir/Path(f['path']).name) if args.audio_dir else f['path']
        tracks.append({'title':report['title'],'path':audio_path,'report_id':report['id'],'audio_sha256':f['sha256'],
                       'end_sec':c['roles']['outgoing']['end_sec'],'source_hashes':report['source_hashes'],
                       'preview_estimation':c['preview_estimation']})
    pairs=[plan(a,b,target_bpm=100,long_intro_policy='silent_preroll',intro_prefix_policy='silent_preroll') for a,b in zip(contracts,contracts[1:])]
    for pair in pairs:
        print(pair['a_title'],'->',pair['b_title'],pair['status'],pair.get('case'),pair.get('overlap_bars'),flush=True)
        if pair['status']=='blocked':raise ValueError(json.dumps(pair['issues'],ensure_ascii=False))
    # Freeze one conservative trim per track, so the next pair cannot change its level mid-song.
    trims=[min([pair['gains'][role+'_trim_db'] for j,pair in enumerate(pairs) for role,idx in [('a',j),('b',j+1)] if idx==i]) for i in range(len(tracks))]
    for i,pair in enumerate(pairs):
        pair['gains'].update(a_trim_db=trims[i],b_trim_db=trims[i+1],set_trim_policy='minimum adjacent trim, fixed throughout track')
        pair['id']=digest({k:v for k,v in pair.items() if k!='id'})
    document={'schema':'harbeat.demo_set_render_plan','version':'1.0-preview','target_bpm':100,
              'order_policy':'supplied folder inventory order; not an optimized ordering claim','tracks':tracks,'pairs':pairs,
              'preview':True,'human_confirmed':False,'source_policy':'Original preprocessing snapshots retained; candidate grid and boundary adjustments only in this audition.'}
    document['id']=digest(document);args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'plan.json').write_text(json.dumps(document,ensure_ascii=False,indent=2))
    (args.output/'contracts.json').write_text(json.dumps(contracts,ensure_ascii=False))
    if not args.plan_only:render(document,args.output,preview=True)
if __name__=='__main__':main()
