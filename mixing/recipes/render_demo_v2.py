#!/usr/bin/env python3
"""Frozen-plan V2 audition with independent acoustic diagnostics."""
import argparse,json,sys,math,hashlib
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from analysis_platform.demo_calibration import extract_features,compare_grids,boundary_evidence
from analysis_platform.demo_preview import candidate
from analysis_platform.demo_v2 import integrated_pair,rank_routes
from analysis_platform.demo_render import render
from analysis_platform.report import digest,validate_report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('outputs/demo-render-v2/listen'));parser.add_argument('--plan-only',action='store_true');parser.add_argument('--calibration-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[2];out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    old=json.loads((root/'outputs/demo-render-v1/listen/plan.json').read_text());other=json.loads((root/'outputs/colleague-demo-review-20260920/mix_plan.json').read_text())
    records=[];contracts=[];calibration=[]
    for t in old['tracks']:
        report=validate_report(json.loads((root/'outputs/demo-render-v1/reports'/(t['audio_sha256']+'.json')).read_text()));c=candidate(report);contracts.append(c);peer=next(x for x in other['tracks'] if x['title']==t['title'])
        end=max(t['end_sec'],peer['first_chorus_end_ms']/1000)+12
        f=extract_features(t['path'],end,out.parent/'feature-cache')
        if f['audio_sha256']!=t['audio_sha256']:raise ValueError('audio identity mismatch')
        seconds=t['end_sec'];pt=np.asarray(c['grid']['beats']);pt=pt[pt<=seconds]
        step=60/peer['bpm'];origin=(peer['intro_end_ms']/1000)%(4*step);peer_ticks=np.arange(origin,seconds,step)
        comparison=compare_grids(pt,peer_ticks,f['onsets'],seconds)
        # Same independent feature extraction; separately report early/late consistency.
        half=seconds/2
        halves=[compare_grids(pt[(pt>=lo)&(pt<hi)]-lo,peer_ticks[(peer_ticks>=lo)&(peer_ticks<hi)]-lo,[v-lo for v in f['onsets'] if lo<=v<hi],hi-lo) for lo,hi in [(0,half),(half,seconds)]]
        comparison['halves']=halves
        role_comparisons={}
        for role,key0,key1 in [('incoming','intro_start_ms','intro_end_ms'),('outgoing','first_chorus_start_ms','first_chorus_end_ms')]:
            lo=max(0,min(c['roles'][role]['start_sec'],peer[key0]/1000));hi=max(c['roles'][role]['end_sec'],peer[key1]/1000)
            anchor=peer[key1]/1000;back=np.arange(anchor,lo-step,-step);back=back[(back>=lo)&(back<=hi)]
            role_comparisons[role]=compare_grids(pt[(pt>=lo)&(pt<=hi)]-lo,np.sort(back)-lo,[v-lo for v in f['onsets'] if lo<=v<=hi],hi-lo)
        comparison['role_comparisons']=role_comparisons
        role_winners=[z['winner'] for z in role_comparisons.values()]
        comparison['full_span_proxy_winner']=comparison['winner']
        comparison['winner']='platform' if 'platform' in role_winners and 'colleague' not in role_winners else 'colleague' if 'colleague' in role_winners and 'platform' not in role_winners else 'inconclusive'
        anchors={'intro_end':'intro_end_ms','chorus_start':'first_chorus_start_ms','chorus_end':'first_chorus_end_ms'}
        boundaries=[boundary_evidence(k,c['anchors'][k]['usable_sec'],peer[v]/1000,f,240/c['preview_estimation']['bpm']) for k,v in anchors.items()]
        # The colleague package omits snap_to_bar and its raw grid. Its tempo-anchor
        # reconstruction is a diagnostic proxy, not an authenticated replacement grid.
        result={'title':t['title'],'audio_sha256':t['audio_sha256'],'report_id':report['id'],'grid_comparison':comparison,
                'compared_grid_definitions':{'platform':'V1 robust regular grid from original preprocessed downbeats','colleague':'constant grid reconstructed from delivered intro end and nominal BPM; package omits snap_to_bar and the original grid'},
                'boundaries':boundaries,'selected_grid':'platform_candidate','selection_reason':'preserve reproducible V1 grid; colleague comparison is a reconstructed proxy, so even a better proxy score is not certified downbeat evidence',
                'section_semantic_winner':'unverifiable_without_annotations','human_confirmed':False,
                'candidate_chorus_bars':c['roles']['outgoing']['bar_count'],
                'unusual_phrase_length':c['roles']['outgoing']['bar_count'] not in (4,8,12,16,24,32),
                'source_first_downbeat_sec':c['preview_estimation']['first_recorded_bar_sec'],'candidate_first_downbeat_sec':c['preview_estimation']['first_bar_sec'],
                'features':f,'review_status':'needs_listening','all_structural_changes_applied':False}
        if comparison['winner']=='platform':result['selection_reason']='platform candidate has stronger measured transient proximity; retained, still no downbeat or semantic confirmation'
        calibration.append(result);records.append((t,report))
        print('acoustic check:',t['title'],comparison['winner'],'coverage',comparison['platform']['coverage_50ms'],comparison['colleague']['coverage_50ms'],flush=True)
    caldoc={'schema':'harbeat.demo_acoustic_comparison','human_reference_available':False,'source_policy':'original files SHA-verified; source reports unchanged','tracks':calibration,
            'method_reference':'https://www.audiolabs-erlangen.de/resources/MIR/FMP/C4/C4S4_NoveltySegmentation.html',
            'method_note':'nearby feature-change diagnostics inspired by novelty analysis; not a trained section-label estimator or ground-truth accuracy score'}
    (out/'calibration.json').write_text(json.dumps(caldoc,ensure_ascii=False,indent=2))
    if args.calibration_only:return
    meta=[{'camelot':r['summary'].get('camelot'),'drums':r['documents']['core']['analysis'].get('drum_groups',{})} for t,r in records]
    edges={(i,j):integrated_pair(contracts[i],contracts[j],meta[i],meta[j]) for i in range(len(records)) for j in range(len(records)) if i!=j}
    rankings=rank_routes(len(records),edges)
    if not rankings:raise ValueError('no valid route')
    order=rankings[0]['order'];pairs=[edges[i,j] for i,j in zip(order,order[1:])];selected=[contracts[i] for i in order]
    tracks=[{**records[i][0],'end_sec':contracts[i]['roles']['outgoing']['end_sec'],'preview_estimation':contracts[i]['preview_estimation']} for i in order]
    trims=[min([p['gains'][side+'_trim_db'] for j,p in enumerate(pairs) for side,k in [('a',j),('b',j+1)] if k==i]) for i in range(len(tracks))]
    for i,p in enumerate(pairs):
        p['gains']['pair_trims_before_set_consistency']={'a':p['gains']['a_trim_db'],'b':p['gains']['b_trim_db']}
        p['gains'].update(a_trim_db=trims[i],b_trim_db=trims[i+1],set_trim_policy='minimum adjacent trim, fixed throughout track')
        p['id']=digest({k:v for k,v in p.items() if k!='id'})
    route_doc={'schema':'harbeat.demo_route_search','input_order':[t['title'] for t,r in records],'permutations_considered':math.factorial(len(records)),
               'valid_routes':len(rankings),'ranking':rankings,'chosen_order':order,'edges':[{'a_index':i,'b_index':j,'plan':p} for (i,j),p in edges.items()],
               'weights_are_heuristics':True,'degraded_drum_evidence_excluded':True,'note':'No claim that the highest heuristic score is the best sounding route.'}
    (out/'routes.json').write_text(json.dumps(route_doc,ensure_ascii=False,indent=2))
    document={'schema':'harbeat.demo_set_render_plan','version':'2.0-preview','target_bpm':100,'tracks':tracks,'pairs':pairs,
              'preview':True,'human_confirmed':False,'order_policy':'exhaustive 720-route heuristic search; detailed scores in routes.json',
              'calibration_id':digest(caldoc),'source_policy':'candidate grid unchanged unless independently verified; unresolved boundaries remain flagged',
              'changes':['automatic order','audible-window mapped vocal intersection','attenuation-only low-frequency exchange','independent acoustic diagnostics']}
    document['id']=digest(document)
    (out/'plan.json').write_text(json.dumps(document,ensure_ascii=False,indent=2));(out/'contracts.json').write_text(json.dumps(selected,ensure_ascii=False))
    print('V2 route:',' -> '.join(x['title'] for x in tracks),flush=True)
    if not args.plan_only:
        execution=render(document,out,preview=True)
        for suffix in ('wav','mp3'):
            (out/('HarBeat-DEMO-1.0-preview.'+suffix)).replace(out/('HarBeat-DEMO-2.0-preview.'+suffix))
        execution['outputs']={'wav':'HarBeat-DEMO-2.0-preview.wav','mp3':'HarBeat-DEMO-2.0-preview.mp3'}
        (out/'execution.json').write_text(json.dumps(execution,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
