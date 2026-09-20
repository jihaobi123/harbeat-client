#!/usr/bin/env python3
"""NAS Hip-Hop audition using the confirmed original colleague DSP policy."""
import argparse,dataclasses,hashlib,itertools,json,math,shutil,statistics,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from analysis_platform.colleague_policy import load_policy,SOURCE
from analysis_platform.demo_v3 import load_renderer,sha256
from analysis_platform.demo_render import measure
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'outputs/hiphop-v3';INPUT=BASE/'inputs';OUT=BASE/'listen';WORK=BASE/'work'

def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2))

def main():
    global BASE, INPUT, OUT, WORK
    parser=argparse.ArgumentParser();parser.add_argument('--plan-only',action='store_true');parser.add_argument('--data-dir',type=Path,default=BASE);args=parser.parse_args()
    BASE=args.data_dir.resolve();INPUT=BASE/'inputs';OUT=BASE/'listen';WORK=BASE/'work'
    OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
    inputs=json.loads((INPUT/'inputs.json').read_text());records=[];grids={};excluded=[]
    for x in inputs:
        reportpath=INPUT/'reports'/(x['report_id']+'.json');r=json.loads(reportpath.read_text());core=r['documents']['core'];a=core['analysis'];audio=INPUT/x['relative_path']
        if sha256(audio)!=x['sha256'] or sha256(reportpath)!=x['report_file_sha256']:raise ValueError('input identity mismatch')
        if core['assets']['master']['sha256']!=x['sha256']:raise ValueError('master differs from published manifest')
        sections=a['sections'];bars=[v/1000 for v in a['beat_grid']['bars_ms']];bpm=a['tempo']['bpm'];median_bpm=240/statistics.median([y-z for z,y in zip(bars,bars[1:])])
        if abs(median_bpm/bpm-1)>.05:
            excluded.append({'title':r['title'],'reason':'标注 BPM 与拍网格中位小节间隔相差超过 5%，本次排除','bpm':bpm,'grid_median_bpm':median_bpm});continue
        if sections.get('source')!='songformer' or sections.get('fallback_used'):raise ValueError('needs real SongFormer structure')
        if not sections['items'] or sections['items'][0]['label']!='intro':raise ValueError('missing intro')
        vocal=r['documents'].get('vocal_activity')
        if not isinstance(vocal,dict) or not isinstance(vocal.get('intervals'),list):raise ValueError('unknown vocal timing')
        vsource=vocal.get('source') or {}
        if vsource.get('track_id')!=core['track_id'] or vsource.get('analysis_run_id')!=core['analysis_run_id']:raise ValueError('vocal run binding mismatch')
        if vocal.get('status')!='ready' or vsource.get('vocal_sha256')!=core['assets']['stems']['vocals']['sha256']:raise ValueError('vocal asset binding mismatch')
        genre=r['extensions']['genre'];top=genre['data']['top']
        if genre.get('status')!='ready' or top[0]['parent']!='Hip Hop':raise ValueError('not a model-first Hip Hop candidate')
        grids[core['track_id']]=bars
        records.append({'input':x,'report':r,'core':core,'audio_path':audio,'bar_bpm':median_bpm})
    if len(records)!=6:raise ValueError(f'expected 6 eligible tracks, got {len(records)}')
    api=load_policy(grids);bundles=[];vocal_reports={}
    for r in records:
        c=r['core'];track=api['manifest_to_track_profile'](c,style='hiphop',title=r['report']['title'],artist=c['source'].get('artist'))
        bundle=SimpleNamespace(track=track,manifest=c);bundles.append(bundle)
        vocal_reports[track.id]=[(z['start_ms'],z['end_ms']) for z in r['report']['documents']['vocal_activity']['intervals']]
        intro=api['first_intro_window'](bundle);chorus=api['first_chorus_block'](bundle)
        if intro.end_ms<=intro.start_ms or chorus.end_ms<=chorus.start_ms:raise ValueError('nonpositive structural window')
        r.update(bundle=bundle,intro=intro,chorus=chorus)
    edges={};invalid={}
    for i,j in itertools.permutations(range(6),2):
        t=api['transition_for_pair'](1,bundles[i],bundles[j],vocal_reports);reason=None
        if t.incoming_source_overlap_ms<2000:reason='所需 B 前奏尾段缺少原始小节网格；候选落到前奏末端，无法形成有效重叠'
        if t.a_chorus_bars<t.b_intro_bars and t.incoming_source_overlap_ms/1000/(240/bundles[j].track.bpm)<min(4,t.a_chorus_bars)-.6:reason='情况三所需的前奏末尾小节未被原网格覆盖'
        if t.overlap_seconds>(t.a_exit_ms-t.a_chorus_start_ms)/1000+.1:reason='实际重叠超过 A 第一遍副歌窗口'
        edges[i,j]=t
        if reason:invalid[i,j]=reason
    rankings=[]
    for order in itertools.permutations(range(6)):
        ts=[edges[i,j] for i,j in zip(order,order[1:])];start=max(0.,104.-bundles[order[0]].track.bpm)/120.
        trend=sum(.025 if bundles[j].track.bpm>=bundles[i].track.bpm else -.045 for i,j in zip(order,order[1:]))
        reason=[invalid[i,j] for i,j in zip(order,order[1:]) if (i,j) in invalid]
        rankings.append({'order':list(order),'titles':[bundles[i].track.title for i in order],'score':start+trend+sum(t.score for t in ts),'start_bonus':start,'trend_bonus':trend,'valid':not reason,'rejection_reasons':reason})
    rankings.sort(key=lambda r:(-r['score'],[t.lower() for t in r['titles']]))
    winner=next((r for r in rankings if r['valid']),None)
    if winner is None:raise ValueError('no renderable route')
    order=winner['order'];ordered=[records[i] for i in order];ts=[dataclasses.replace(edges[i,j],position=k+1) for k,(i,j) in enumerate(zip(order,order[1:]))]
    trackrows=[];pairrows=[]
    for i,r in enumerate(ordered):
        t=r['bundle'].track;incoming=ts[i-1] if i else None;outgoing=ts[i] if i<5 else None;c=r['core'];intro=r['intro'];chorus=r['chorus']
        params={'entry_ms':incoming.b_entry_ms if incoming else 0,'exit_ms':chorus.end_ms,'incoming_source_overlap_ms':incoming.incoming_source_overlap_ms if incoming else 0,
                'incoming_rate':incoming.entry_rate if incoming else 1.,'outgoing_overlap_seconds':outgoing.overlap_seconds if outgoing else 0.,'mid_duck':incoming.both_vocal if incoming else False,
                'restore_half_bar_seconds':incoming.restore_half_bar_seconds if incoming else 0.,'final_track':i==5}
        head=params['incoming_source_overlap_ms']/1000;duration=(params['exit_ms']-params['entry_ms'])/1000-head+head/params['incoming_rate']
        raw=c['analysis']['sections']['items'];ci=next(k for k,s in enumerate(raw) if s['label'] in api['CHORUS_LABELS']);ce=raw[ci]['end_ms']
        for nxt in raw[ci+1:]:
            if nxt['label'] not in api['CHORUS_LABELS'] or nxt['start_ms']>ce+100:break
            ce=max(ce,nxt['end_ms'])
        rawintroend=raw[0]['end_ms']
        for nxt in raw[1:]:
            if nxt['label']!='intro' or nxt['start_ms']>rawintroend+100:break
            rawintroend=max(rawintroend,nxt['end_ms'])
        trackrows.append({'title':t.title,'artist':t.artist,'track_id':t.id,'report_id':r['report']['id'],'analysis_run_id':c['analysis_run_id'],'audio_sha256':r['input']['sha256'],'source_input_sha256':c['source'].get('input_sha256'),
            'source_path':str(r['audio_path']),'nas_source_path':r['input']['source_path'],'bpm':t.bpm,'key':t.key,'intro':dataclasses.asdict(intro),'chorus':dataclasses.asdict(chorus),
            'raw_boundaries_ms':{'intro_end':rawintroend,'chorus_start':raw[ci]['start_ms'],'chorus_end':ce},
            'snap_changes_ms':{'intro_end':intro.end_ms-rawintroend,'chorus_start':chorus.start_ms-raw[ci]['start_ms'],'chorus_end':chorus.end_ms-ce},
            'grid_source':'published analysis.beat_grid.bars_ms; nearest recorded bar','first_recorded_bar_sec':grids[t.id][0],'grid_median_bpm':r['bar_bpm'],
            'style_evidence':r['report']['extensions']['genre'],'tempo_quality':c['analysis']['tempo'],'source_quality':c.get('quality'),'vocal_source':r['report']['documents']['vocal_activity'],
            'render':params,'planned_segment_duration_sec':duration,'human_confirmed':False})
    offset=0.
    for i,t in enumerate(ts):
        entry=offset+trackrows[i]['planned_segment_duration_sec']-t.overlap_seconds;handoff=offset+trackrows[i]['planned_segment_duration_sec']
        k=api['harmonic_compatibility_score'](ordered[i]['bundle'].track.key,ordered[i+1]['bundle'].track.key);d=api['drum_overlap_score'](ordered[i]['bundle'].track.drum_profile,ordered[i+1]['bundle'].track.drum_profile)
        comp={'base':1.,'tempo_cost':-abs(t.entry_rate-1)*2.6,'case_cost':0 if t.case.startswith('case_1') else -.08 if t.case.startswith('case_2') else -.18,
              'vocal_cost':-(t.a_vocal_ratio*t.b_vocal_ratio*2+(.18 if t.both_vocal else 0)),'key_bonus':k*.13,'drum_bonus':d*.17}
        pairrows.append({**dataclasses.asdict(t),'from_title':trackrows[i]['title'],'to_title':trackrows[i+1]['title'],'score_components':comp,'key_score':k,'drum_score':d,
            'planned_entry_sec':entry,'planned_handoff_sec':handoff,'planned_b_eq_restore_sec':handoff-t.restore_half_bar_seconds,
            'a_vocal_intervals_source_ms':vocal_reports[t.from_track_id],'b_vocal_intervals_source_ms':vocal_reports[t.to_track_id],
            'vocal_policy':'original both-window presence: each padded 300 ms; at least 500 ms and 5%; not V2 simultaneous intersection',
            'eq':{'b_bass_db':-7,'b_treble_db':1.2,'b_mid_db':-5 if t.both_vocal else 0,'a_bass_db':-9,'a_treble_db':-1.4,'bass_hz':140,'treble_hz':3600,'mid_hz':1200,'mid_q':1.05,'restore':'wet-to-dry crossfade final half bar'},
            'gain':{'fixed_each_track':.76,'fade':'linear amplitude','limiter':{'limit':.96,'level':False}}})
        offset=entry
    doc={'schema':'harbeat.hiphop_colleague_v3_plan','version':'hiphop-v3-1','tracks':trackrows,'transitions':pairrows,'policy_provenance':api['provenance'],
         'human_confirmed':False,'selection':{'model_requirement':'Discogs400 top1 parent exactly Hip Hop','shortlist':7,'selected':6,'tempo_range':[min(t['bpm'] for t in trackrows),max(t['bpm'] for t in trackrows)],'excluded':excluded,
          'reason':'Existing SongFormer intro/chorus and manifest-bound vocal intervals; comparable BPM; exclude marked grid inconsistency. Existing manual genre and other model candidates remain in catalog audit.'},
         'ranking':{'permutations':720,'valid':sum(r['valid'] for r in rankings),'selected':winner,'unconstrained_winner':rankings[0],'complete_record':'routes.json'},
         'source_policy':'NAS read-only snapshots; no reanalysis or rewriting of source labels; explicit bar adapter for absent colleague helper',
         'audio_policy':'Pinned original colleague renderer, verified by the confirmed Future Bass V3 baseline; no V2 fixed-tempo or per-track trim/FIR policy'}
    doc['id']=hashlib.sha256(json.dumps(doc,sort_keys=True).encode()).hexdigest()
    save(OUT/'plan.json',doc);save(OUT/'routes.json',{'ranking':rankings,'rejected_pairs':[{'from':bundles[i].track.title,'to':bundles[j].track.title,'reason':reason} for (i,j),reason in invalid.items()]})
    print('SELECTED:',winner['titles'],'valid routes',sum(r['valid'] for r in rankings),flush=True)
    print('Transitions:',[(t.from_track_id,t.case,t.overlap_seconds,t.both_vocal) for t in ts],flush=True)
    if args.plan_only:return
    commands=[];render=load_renderer(SOURCE,commands);ffmpeg=render['_ffmpeg']();segments=[];execrows=[]
    for i,t in enumerate(trackrows):
        path=WORK/f'segment-{i+1:02d}.wav';segments.append(path);print('Rendering',i+1,t['title'],flush=True)
        render['render_segment'](ffmpeg=ffmpeg,source_path=Path(t['source_path']),output_path=path,**t['render']);info=sf.info(path)
        execrows.append({'title':t['title'],'frames':info.frames,'duration_sec':info.duration,'planned_duration_sec':t['planned_segment_duration_sec'],'duration_difference_ms':(info.duration-t['planned_segment_duration_sec'])*1000,'sha256':sha256(path)})
    wav=OUT/'HarBeat-HipHop-6-V3.wav';mp3=OUT/'HarBeat-HipHop-6-V3.mp3';overlaps=[t.overlap_seconds for t in ts]
    times,duration=render['render_crossfaded_mix'](ffmpeg,segments,overlaps,wav);snippets=render['render_snippets'](ffmpeg,wav,times,WORK/'snippets')
    for src,dest in [(wav,mp3)]+[(s,OUT/f'transition-{i+1:02d}.mp3') for i,s in enumerate(snippets)]:render['_run']([ffmpeg,'-y','-v','error','-i',str(src),'-c:a','libmp3lame','-b:a','320k',str(dest)])
    events=[]
    for i,t in enumerate(pairrows):
        for name,planned,actual in [('进歌',t['planned_entry_sec'],times[i]),('交接完成',t['planned_handoff_sec'],times[i]+t['overlap_seconds']),('B EQ 开始恢复',t['planned_b_eq_restore_sec'],times[i]+t['overlap_seconds']-t['restore_half_bar_seconds'])]:
            events.append({'transition':i+1,'event':name,'planned_sec':planned,'render_timeline_sec':actual,'difference_ms':(actual-planned)*1000,'basis':'measured segment lengths through original renderer; EQ/tempo block rounding and limiter latency not independently instrumented; not browser telemetry'})
    execution={'schema':'harbeat.hiphop_v3_execution','plan_id':doc['id'],'duration_sec':duration,'tracks':execrows,'events':events,'commands':commands,
               'wav_levels':measure(wav),'mp3_levels':measure(mp3),'wav_sha256':sha256(wav),'mp3_sha256':sha256(mp3),'source_hashes_verified':True,'original_renderer_unchanged':True,'reference_audio_for_this_set':None}
    save(OUT/'execution.json',execution);print('COMPLETE',duration,execution['mp3_levels'],flush=True)
if __name__=='__main__':main()
