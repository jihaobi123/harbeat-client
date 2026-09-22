"""Additive, source-bound section/window evidence. No semantic ground truth implied."""
import math

VERSION = 'harbeat.mix_profiles.v1'
POLICY = {'energyUnit': 'dBFS_RMS', 'calibrationId': 'master-rms-common-digital-full-scale-v1',
          'preSec': 4, 'sustainSec': 16, 'blockSec': 4, 'minimumDeltaDb': 1,
          'maximumJumpDb': 6, 'minimumStyleSec': 8, 'minimumStyleScore': .10,
          'minimumStyleMargin': .015, 'minimumCoverage': .98}


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def measure(rows, start, end):
    """Nonoverlapping measurement frames only; missing data never counts as silence."""
    power = covered = 0.; last = -math.inf; invalid = False
    if not finite(start) or not finite(end) or end <= start:
        return {'start': start, 'end': end, 'dbfs': None, 'coverage': 0, 'status': 'missing'}
    for r in rows:
        s, e, db = r.get('start'), r.get('end'), r.get('rms_dbfs')
        if not finite(s) or not finite(e) or e <= s: invalid = True; continue
        if e <= start or s >= end: continue
        if s < last - 1e-6: invalid = True
        last = e
        if not finite(db): continue
        w = max(0., min(end,e)-max(start,s)); power += w*10**(db/10); covered += w
    coverage = min(1., covered/(end-start))
    ok = not invalid and coverage >= POLICY['minimumCoverage'] and power > 0
    return {'start':start, 'end':end, 'dbfs':10*math.log10(power/covered) if ok else None,
            'coverage':coverage, 'status':'measured' if ok else 'missing'}


def inference_intervals(intervals, duration):
    if not finite(duration) or duration <= 0 or len(intervals) > 256:
        raise ValueError('invalid interval count or audio duration')
    result = []
    for r in intervals:
        s,e = r.get('start'),r.get('end')
        if not finite(s) or not finite(e) or s < 0 or e <= s or e > duration+.001 or e-s > 120:
            raise ValueError('genre interval outside source / over 120 seconds')
        pair = (round(s*16000), min(round(e*16000),round(duration*16000)))
        if e-s >= POLICY['minimumStyleSec'] and pair not in result: result.append(pair)
    return result


def style_evidence(segments, start, end):
    relevant = [r for r in segments if r['end'] > start and r['start'] < end]
    exact = [r for r in relevant if abs(r['start']-start)<.002 and abs(r['end']-end)<.002]
    r = exact[0] if exact else (max(relevant,key=lambda x:min(end,x['end'])-max(start,x['start'])) if relevant else {})
    top = r.get('top',[]); scores = [x.get('score') for x in top]
    valid = bool(scores) and all(finite(x) and 0 <= x <= 1 for x in scores)
    margin = scores[0] - scores[1] if valid and len(scores)>1 else None
    reasons=[]
    if end-start < POLICY['minimumStyleSec']: reasons.append('short_context')
    if not exact: reasons.append('not_direct_interval_inference')
    if not valid or scores[0]<POLICY['minimumStyleScore']: reasons.append('weak_model_score')
    if margin is None or margin < POLICY['minimumStyleMargin']: reasons.append('ambiguous_candidates')
    if r.get('patch_count',0) < 3: reasons.append('insufficient_patches')
    return {'start':start,'end':end,'status':'needs_review' if reasons else 'model_candidate',
            'top':top,'margin':margin,'reasons':reasons,
            'support':[{'start':x['start'],'end':x['end'],'patchCount':x.get('patch_count',0)} for x in relevant],
            'definition':'未校准模型候选；阈值是实验筛选规则，不是识别准确率；短片段不继承整曲标签'}


def requested_intervals(track):
    duration=track['duration']; result=[]
    for s in track['sections']:
        if 0 <= s['start'] < duration:
            # Large sections are split only for inference; never change original structure.
            start=s['start']; end=min(s['end'],duration)
            while start < end:
                result.append({'start':start,'end':min(end,start+120)}); start+=120
    for w in track['windows']:
        result.extend([{'start':w['start'],'end':w['end']},
                       {'start':w['end'],'end':min(duration,w['end']+POLICY['sustainSec'])}])
    return result


def build_profiles(report, track, local_genre=None):
    core=report['documents']['core']
    master=core['assets']['master']['sha256']
    if track.get('reportId') and report.get('id')!=track['reportId']: raise ValueError('report ID mismatch')
    if core.get('analysis',{}).get('sections',{}).get('items') is not None:
        sections=[{'start':v['start_ms']/1000,'end':v['end_ms']/1000,'label':v['label']} for v in core['analysis']['sections']['items']]
        if sections!=track['sections']: raise ValueError('catalog/report section geometry mismatch')
    if track.get('provenance',{}).get('masterSha256') != master: raise ValueError('catalog/master SHA mismatch')
    ext=report.get('extensions',{}); dj=ext.get('dj_signals',{})
    data=dj.get('data',{}) if dj.get('status')=='ready' else {}
    if data and data.get('audio_sha256') != master: raise ValueError('DJ measurement SHA mismatch')
    genre=local_genre or ext.get('genre',{}); gd=genre.get('data',{}) if genre.get('status')=='ready' else {}
    if gd and gd.get('audio_sha256')!=master: raise ValueError('genre SHA mismatch')
    rows=data.get('rms_points',[]); duration=track['duration']
    curve=[]
    for i in range(math.ceil(duration*2)):
        m=measure(rows,i*.5,min(duration,(i+1)*.5))
        curve.append(m)
    segments=gd.get('segments',[])
    def interval(start,end):
        overlaps=[{'index':i,'label':s['label'],'start':max(start,s['start']),'end':min(end,s['end'])}
                  for i,s in enumerate(track['sections']) if s['end']>start and s['start']<end]
        return {'start':start,'end':end,'energy':measure(rows,start,end), 'style':style_evidence(segments,start,end),
                'sections':overlaps,'boundaryStatus':'model_boundaries_unconfirmed'}
    sections=[dict(index=i,label=s['label'],**interval(s['start'],min(s['end'],duration)))
              for i,s in enumerate(track['sections']) if 0 <= s['start'] < min(s['end'],duration)]
    windows=[]
    for w in track['windows']:
        end=w['end']; body_end=min(duration,end+POLICY['sustainSec'])
        windows.append({'id':w['id'],'entry':interval(w['start'],end),'takeover':interval(end,body_end),
                        'sustain':[measure(rows,end+i*4,end+(i+1)*4) for i in range(4)]})
    return {'schema':VERSION,'policy':POLICY.copy(),'source':{'reportId':report['id'],'masterSha256':master,
            'sectionSource':report['documents']['core'].get('analysis',{}).get('sections',{}).get('source'),
            'measurementMethod':data.get('method'), 'genreModels':gd.get('model_files',{}),
            'genreAggregation':gd.get('aggregation'),'catalogReportSha256':track.get('provenance',{}).get('reportSha256'),
            'geometryBinding':'exact equality with core section intervals; existing catalog report and current report file digests retained separately'},
            'energyFrames':[{'start':r['start'],'end':r['end'],'dbfs':r.get('rms_dbfs'),
                             'coverage':1 if finite(r.get('rms_dbfs')) else 0,
                             'status':'measured' if finite(r.get('rms_dbfs')) else 'missing'}
                            for r in rows if r['start']<duration],
            'energyCurve':curve,'sections':sections,'windows':windows,
            'limitations':['能量是统一数字满刻度下的原曲 RMS 功率；尚未进行跨曲听感标定',
            '比较转场前 A 与接管后 B 的原曲窗口，沿用相同 V3 主增益；不是混合输出或扬声器实测',
            'SongFormer 段落边界仍未经人工确认；对齐不会把候选变成标准答案',
            '局部风格分数不代表概率；保留所有原始模型输出和原有规则／人工标签']}
