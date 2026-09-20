"""Versioned DJ input, derived without replacing any source analysis.

All timestamps are seconds on the original recording, intervals are half-open.
Candidate recognition and human confirmation are deliberately separate.
"""
from bisect import bisect_left
import math
from statistics import median
from .report import digest, intervals

VERSION = 'dj_preprocessing_v1'
ANCHORS = ('intro_start','intro_end','verse_start','chorus_start','chorus_end')
ANCHOR_NAMES = dict(zip(ANCHORS,('前奏开始','前奏结束','第一遍主歌开始','第一遍副歌开始','第一遍副歌结束')))


def number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def issue(code,message,severity='blocked'):
    return {'code':code,'message':message,'severity':severity}


def points(values,duration):
    return sorted(set(float(v) for v in values or [] if number(v) and 0<=v<=duration))


def nearest_distance(values,t):
    i=bisect_left(values,t)
    return min((abs(v-t) for v in values[max(0,i-1):i+1]),default=999)


def core_of(report):
    doc=report['documents'].get(report.get('primary_source','core'),{})
    return doc.get('analysis',doc)


def source_fingerprint(report):
    # Unrelated mood/genre recomputation must not erase checked beat/section edits.
    core=core_of(report)
    return digest({'version':VERSION,'audio_sha256':report['audio'].get('sha256'),
        'vocal_asset_id':report['audio'].get('assets',{}).get('vocals',{}).get('id'),
        'duration':report['summary'].get('duration'),
        'core':{k:core.get(k) for k in ('sections','phrase_map','beat_grid','beat_points','downbeats','time_signature','beat_confidence','beat_needs_review','tempo','bpm')},
        'timeline':{k:report['timeline'].get(k) for k in ('beats','downbeats','sections')},
        'songformer':report['documents'].get('songformer-sections'),
        'vocal_activity':report['documents'].get('vocal_activity'),
        'signals':report['extensions'].get('dj_signals',{}).get('data')})


def structure(report):
    core=core_of(report);songformer=report['documents'].get('songformer-sections',{})
    if songformer.get('status')=='ready' and songformer.get('segments'):
        source,items='songformer-sections',intervals(songformer['segments'])
    elif core.get('sections'):
        source,items='core.sections',intervals(core['sections'])
    else:
        source,items='legacy.phrase_map',intervals(core.get('phrase_map') or report['timeline'].get('sections'))
    items=sorted(items,key=lambda s:s['start'])
    # Adjacent equal labels can be model chunks of the same musical episode.
    episodes=[]
    for s in items:
        s={**s,'label':s['label'].strip().lower()}
        if episodes and episodes[-1]['label']==s['label'] and abs(episodes[-1]['end']-s['start'])<=.001:
            episodes[-1]['end']=s['end'];episodes[-1]['parts'].append(s)
        else:episodes.append({**s,'parts':[s]})
    intro=next((s for s in episodes if s['label']=='intro'),None)
    verse=next((s for s in episodes if s['label']=='verse'),None)
    chorus=next((s for s in episodes if s['label']=='chorus'),None)
    anchors={'intro_start':intro['start'] if intro else None,'intro_end':intro['end'] if intro else None,
             'verse_start':verse['start'] if verse else None,'chorus_start':chorus['start'] if chorus else None,
             'chorus_end':chorus['end'] if chorus else None}
    return {'source':source,'segments':items,'episodes':episodes},anchors


def grid(report,edit=None):
    duration=report['summary'].get('duration') or report['audio'].get('duration') or 0
    core=core_of(report);raw=core.get('beat_grid') or {};timeline=report['timeline']
    meter=core.get('time_signature') or raw.get('time_signature') or {}
    edit=edit or {}
    beats=points(edit.get('beats',timeline.get('beats')),duration)
    downbeats=points(edit.get('downbeats',timeline.get('downbeats') or [x/1000 for x in raw.get('bars_ms',[])]),duration)
    numerator=edit.get('numerator',meter.get('numerator'));denominator=edit.get('denominator',meter.get('denominator'))
    issues=[]
    if numerator!=4 or denominator!=4:issues.append(issue('meter_unsupported','第一版需要确认 4/4 拍；缺失拍号和其他拍号不能按每小节四拍处理'))
    if len(beats)<8 or len(downbeats)<2:issues.append(issue('grid_missing','缺少足够拍点或小节首拍'))
    diffs=[b-a for a,b in zip(beats,beats[1:])];step=median(diffs) if diffs else None
    bpm=60/step if step and step>0 else None
    bars=[]
    for i,(start,end) in enumerate(zip(downbeats,downbeats[1:])):
        lo=bisect_left(beats,start-.025);hi=bisect_left(beats,end-.025)
        ticks=beats[lo:hi]
        start_error=nearest_distance(beats,start)
        end_error=nearest_distance(beats,end)
        complete=bool(numerator==4 and denominator==4 and len(ticks)==4 and start_error<=.025 and end_error<=.025)
        bars.append({'index':i+1,'start':start,'end':end,'beats':ticks,'beat_count':len(ticks),
                     'complete':complete,'bpm':240/(end-start),'first_beat_index':lo})
    if not edit and (core.get('beat_needs_review') or raw.get('needs_review') or (core.get('tempo') or {}).get('needs_review')):
        issues.append(issue('source_grid_review','原分析标记拍网格需要复核','needs_review'))
    return {'source':'human_grid' if edit else 'original_beat_grid','numerator':numerator,'denominator':denominator,
            'beats':beats,'downbeats':downbeats,'bars':bars,'bpm':bpm,
            'leading_uncovered_sec':downbeats[0] if downbeats else duration,
            'trailing_uncovered_sec':max(0,duration-downbeats[-1]) if downbeats else duration,
            'status':'blocked' if any(x['severity']=='blocked' for x in issues) else 'candidate','issues':issues}


def vocal_data(report,signals):
    source=report['documents'].get('vocal_activity') or {}
    duration=report['summary'].get('duration') or 0
    if source.get('status')=='ready' and source.get('time_origin')=='master_audio_start' and isinstance(source.get('intervals'),list):
        source_duration=source.get('duration_ms',0)/1000
        regions=intervals(source['intervals'])
        valid=len(regions)==len(source['intervals']) and all(0<=r['start']<r['end']<=duration+.001 for r in regions)
        valid=valid and all(a['end']<=b['start'] for a,b in zip(regions,regions[1:]))
        source_sha=(source.get('source') or {}).get('vocal_sha256')
        measured_sha=(signals.get('vocals',{}).get('asset') or {}).get('verified_sha256')
        binding_ok=not (source_sha and measured_sha and source_sha!=measured_sha)
        if abs(source_duration-duration)<=.1 and valid and binding_ok:
            return {'status':'candidate','source':'vocal_activity','intervals':regions,
                    'coverage_sec':source_duration,'producer':source.get('producer'),
                    'needs_review':True,'limitations':source.get('quality_flags',[]),
                    'definition':'已有分离人声上的 VAD 候选；需试听核对演唱、伴唱与漏检'}
    fallback=signals.get('vocals') or {}
    regions=fallback.get('intervals');coverage=fallback.get('coverage_sec')
    if fallback.get('status')=='candidate' and isinstance(regions,list) and number(coverage) and abs(coverage-duration)<=.1:
        valid=all(isinstance(r,dict) and number(r.get('start')) and number(r.get('end')) and 0<=r['start']<r['end']<=duration+.001 for r in regions)
        if valid and all(a['end']<=b['start'] for a,b in zip(regions,regions[1:])):return fallback
    return {'status':'unavailable','source':None,'intervals':None,'coverage_sec':0,
            'definition':'人声时间区间未知；不能视为无人声'}


def attach_bar_measurements(bars,vocals,signals):
    rows=signals.get('rms_points') or [];starts=[p['start'] for p in rows]
    regions=vocals.get('intervals');ends=[p['end'] for p in regions or []]
    for bar in bars:
        start,end=bar['start'],bar['end'];active=None
        if regions is not None:
            lo=bisect_left(ends,start)
            active=0.
            for p in regions[lo:]:
                if p['start']>=end:break
                active+=max(0,min(end,p['end'])-max(start,p['start']))
        bar['vocal_active_sec']=active
        bar['vocal_ratio']=active/(end-start) if active is not None else None
        lo=max(0,bisect_left(starts,start)-1);hi=bisect_left(starts,end)
        selected=[(p,max(0,min(end,p['end'])-max(start,p['start']))) for p in rows[lo:hi]]
        covered=sum(w for _,w in selected)
        bar['signal_coverage_sec']=covered
        def energy(field):
            if covered<end-start-.001:return None
            total=0.
            for p,w in selected:
                value=p.get('rms_dbfs') if field=='rms' else (p.get('bands_dbfs') or {}).get(field)
                if number(value):total+=10**(value/10)*w
            return 10*math.log10(total/covered) if total>0 and covered else None
        bar['rms_dbfs']=energy('rms');bar['bands_dbfs']={k:energy(k) for k in ('low','mid','high')}


def build(report,review=None):
    fingerprint=source_fingerprint(report)
    fresh=bool(review and review.get('source_fingerprint')==fingerprint)
    edit=review if fresh else {}
    checks=edit.get('confirmations') or {}
    g=grid(report,edit.get('grid'));s,raw=structure(report)
    duration=report['summary'].get('duration') or 0
    tolerance=min(.15,60/g['bpm']*.2) if g['bpm'] else .1
    anchors={}
    for name in ANCHORS:
        value=(edit.get('anchors') or {}).get(name,raw[name])
        nearest=min(g['downbeats'],key=lambda t:abs(t-value)) if value is not None and g['downbeats'] else None
        usable=nearest if nearest is not None and abs(nearest-value)<=tolerance and 0<=value<=duration else None
        anchors[name]={'raw_sec':raw[name],'edited_sec':(edit.get('anchors') or {}).get(name),
                       'suggested_sec':nearest,'usable_sec':usable,
                       'snap_delta_ms':round((nearest-value)*1000,3) if nearest is not None else None,
                       'source':'human_anchor' if name in (edit.get('anchors') or {}) else s['source']}
    module=report['extensions'].get('dj_signals',{})
    signals=module.get('data') or {}
    signal_current=module.get('status')=='ready' and signals.get('audio_sha256')==report['audio'].get('sha256') and bool(report['audio'].get('sha256'))
    expected_stem=report['audio'].get('assets',{}).get('vocals',{}).get('id')
    measured_stem=signals.get('vocal_asset_id',(signals.get('vocals',{}).get('asset') or {}).get('id'))
    if expected_stem!=measured_stem:signal_current=False
    if not signal_current:signals={}
    vocals=vocal_data(report,signals)
    if 'vocal_intervals' in edit:
        vocals={**vocals,'intervals':edit['vocal_intervals'],'source':'human_intervals','status':'candidate','coverage_sec':duration}
    vocals={**vocals,'confirmed':bool(checks.get('vocals')) and vocals['status']!='unavailable'}
    attach_bar_measurements(g['bars'],vocals,signals)
    roles={}
    for role,keys in [('incoming',('intro_start','intro_end','verse_start')),('outgoing',('chorus_start','chorus_end'))]:
        issues=[x for x in g['issues'] if not (checks.get('grid') and x['code']=='source_grid_review')];values={k:anchors[k]['usable_sec'] for k in keys}
        for k in keys:
            if values[k] is None:issues.append(issue('anchor_'+k,'关键边界缺失或距离首拍过远：'+ANCHOR_NAMES[k]))
        if role=='incoming':
            intro_end=(edit.get('anchors') or {}).get('intro_end',raw['intro_end'])
            verse_start=(edit.get('anchors') or {}).get('verse_start',raw['verse_start'])
            if intro_end is not None and verse_start is not None and abs(intro_end-verse_start)>tolerance:
                issues.append(issue('intro_not_followed_by_verse','前奏结束后不是第一遍主歌，不能套用本版出歌点定义'))
        start,end=(values.get('intro_start'),values.get('intro_end')) if role=='incoming' else (values.get('chorus_start'),values.get('chorus_end'))
        selected=[]
        if start is not None and end is not None:
            if end<=start:issues.append(issue('invalid_role_range','段落结束必须晚于开始'))
            selected=[b for b in g['bars'] if b['start']>=start-.001 and b['end']<=end+.001]
            if not selected or any(not b['complete'] for b in selected) or abs(sum(b['end']-b['start'] for b in selected)-(end-start))>.025:
                issues.append(issue('partial_bars','衔接段落包含残缺或拍数不一致的小节，需校准拍网格'))
        if not report['audio'].get('sha256') or report['audio'].get('hash_verification') not in ('verified','hash_verified'):
            issues.append(issue('audio_unverified','需要核验原曲指纹后才能绑定接歌输入'))
        if not signal_current or not signals.get('local_loudness'):
            issues.append(issue('local_loudness_missing','尚无本音频的局部响度和采样峰值，请运行接歌预处理'))
        if vocals['status']=='unavailable':issues.append(issue('vocals_missing','缺少可用人声时间区间，不能自动决定中频衰减'))
        for check,label in [('structure','段落边界'),('grid','拍点与小节'),('vocals','人声区间')]:
            if not checks.get(check):issues.append(issue('review_'+check,label+'尚未试听确认','needs_review'))
        state='blocked' if any(x['severity']=='blocked' for x in issues) else 'needs_review' if issues else 'ready'
        roles[role]={'status':state,'issues':issues,'start_sec':start,'end_sec':end,'bar_count':len(selected) if selected else None,
                     'bar_indices':[b['index'] for b in selected]}
    result={'schema':'harbeat.dj_preprocessing','version':VERSION,'report_id':report['id'],'title':report['title'],
            'audio_sha256':report['audio'].get('sha256'),'duration':duration,'source_fingerprint':fingerprint,
            'time_origin':'master_audio_start','interval_convention':'[start,end)','unit':'seconds',
            'grid':g,'structure':s,'anchors':anchors,'vocals':vocals,'signals':signals,'roles':roles,
            'review':{'status':'current' if fresh else 'stale' if review else 'not_reviewed',
                      'revision':review.get('revision',0) if review else 0,'current':review},
            'source_hashes':report['source_hashes'],'key':report['summary'].get('key'),
            'limitations':['拍点吸附容差不代表模型精度','人声候选需核对演唱漏检与分离泄漏','采样峰值不等于真峰值；混音渲染后需再测量']}
    result['id']=digest(result)
    return result
