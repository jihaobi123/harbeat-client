"""DEMO 1.0 pair planning. No audio is played and no execution time is invented."""
import math
from .dj_contract import issue, number
from .report import digest


def local_loudness(contract,start,end):
    # Only use windows entirely inside the audible region, avoiding an adjacent chorus.
    rows=[p for p in contract.get('signals',{}).get('local_loudness',[]) if
          p['start']>=start-.001 and p['end']<=end+.001 and number(p.get('lufs'))]
    return 10*math.log10(sum(10**(p['lufs']/10) for p in rows)/len(rows)) if rows else None


def clipped(intervals,start,end,transform):
    return [{'start':transform(max(p['start'],start)),'end':transform(min(p['end'],end))}
            for p in intervals or [] if min(p['end'],end)>max(p['start'],start)]


def plan(a,b,target_bpm=None,long_intro_policy=None,intro_prefix_policy=None):
    if intro_prefix_policy not in (None,'silent_preroll'):raise ValueError('invalid intro prefix policy')
    if long_intro_policy not in (None,'silent_preroll','tail_four_bars'):
        raise ValueError('invalid long intro policy')
    if target_bpm is not None and (not number(target_bpm) or not 40<=target_bpm<=240):
        raise ValueError('目标 BPM 必须在 40–240 之间')
    issues=[{**x,'track':label} for label,c,role in [('A',a,'outgoing'),('B',b,'incoming')]
            for x in c['roles'][role]['issues']]
    result={'schema':'harbeat.dj_transition_plan','version':'demo_1.0','a_contract_id':a['id'],'b_contract_id':b['id'],
            'a_report_id':a['report_id'],'b_report_id':b['report_id'],'a_title':a['title'],'b_title':b['title'],
            'issues':issues,'status':'blocked','events':[], 'execution':{'status':'not_run','clock':None},
            'time_origin':'A playback starts at 0; original audio start, no trimming',
            'policy':{'vocal_trigger':'both_sections_contain_vocals','long_intro':long_intro_policy,'intro_prefix':intro_prefix_policy,
                      'mixing':'full_master_gain_and_attenuation_EQ','requires_prebuffer':True,'preserve_pitch':True}}
    ar=a['roles']['outgoing'];br=b['roles']['incoming']
    ac,bc=ar['bar_count'],br['bar_count']
    if not ac or not bc or any(v is None for v in (ar['start_sec'],ar['end_sec'],br['start_sec'],br['end_sec'])):
        result['id']=digest(result);return result
    a0,a1=ar['start_sec'],ar['end_sec'];b0,b1=br['start_sec'],br['end_sec']
    if a1<=a0 or b1<=b0:
        result['id']=digest(result);return result
    # Endpoint-derived local tempo avoids cumulative bias from rounded beat timestamps.
    abpm=240*ac/(a1-a0);bbpm=240*bc/(b1-b0);target=target_bpm or abpm
    ra,rb=target/abpm,target/bbpm
    handoff=a1/ra
    case='equal' if ac==bc else 'a_longer' if ac>bc else 'b_longer'
    a_bars=[v for v in a['grid']['bars'] if v['index'] in ar['bar_indices']]
    b_bars=[v for v in b['grid']['bars'] if v['index'] in br['bar_indices']]
    count=bc if ac>=bc else 4
    if len(a_bars)<count or len(b_bars)<count:
        issues.append(issue('fewer_than_four_bars','第三种情况要求 A 副歌和 B 前奏均有完整的最后四小节'))
        result['id']=digest(result);return result
    entry=a_bars[-count]['start']/ra
    b_at_entry=b1+(entry-handoff)*rb
    playback_start=handoff-b1/rb
    cue=0.
    if case=='b_longer':
        if long_intro_policy is None:issues.append(issue('long_intro_policy_required','长前奏需要选择静音预播放或裁取最后四小节，不能同时满足全部原规则'))
        if long_intro_policy=='tail_four_bars':playback_start=entry;cue=b_at_entry
    elif b0>0 and intro_prefix_policy!='silent_preroll':
        issues.append(issue('intro_has_prefix','B 前奏之前存在未纳入衔接的小节或弱起；从文件开头播放的可听策略需确认'))
    if playback_start<0:issues.append(issue('preroll_before_a','B 需要在 A 开始之前启动；本计划没有足够的静音预播放时间'))
    if ra<.85 or ra>1.15 or rb<.85 or rb>1.25:
        issues.append(issue('stretch_review','变速幅度较大，需要试听确认音质','needs_review'))
    ta=lambda t:t/ra
    tb=lambda t:handoff+(t-b1)/rb
    a_ticks=[t for bar in a_bars[-count:] for t in bar['beats']]+[a1]
    b_ticks=[t for bar in b_bars[-count:] for t in bar['beats']]+[b1]
    errors=[abs(ta(x)-tb(y))*1000 for x,y in zip(a_ticks,b_ticks)]
    max_error=max(errors,default=0)
    if len(a_ticks)!=len(b_ticks) or max_error>50:
        issues.append(issue('constant_rate_drift','固定变速后拍点最大偏差超过 50ms 或拍数不匹配；需修正拍网格或使用可变速度映射'))
    restore_start=ta(a_bars[-1]['beats'][-2]) if len(a_bars[-1]['beats'])>=2 else None
    av=a['vocals'].get('intervals');bv=b['vocals'].get('intervals')
    a_overlap=clipped(av,entry*ra,a1,ta);b_overlap=clipped(bv,b_at_entry,b1,tb)
    simultaneous=[{'start':max(x['start'],y['start']),'end':min(x['end'],y['end'])}
                  for x in a_overlap for y in b_overlap if min(x['end'],y['end'])>max(x['start'],y['start'])]
    trigger=(bool(clipped(av,a0,a1,ta)) and bool(clipped(bv,b0,b1,tb))) if av is not None and bv is not None else None
    al=local_loudness(a,entry*ra,a1);bl=local_loudness(b,b_at_entry,b1)
    if al is None or bl is None:issues.append(issue('transition_loudness_missing','实际衔接窗口缺少完整的 3 秒局部响度窗口'))
    ga=min(0,-18-al) if al is not None else None;gb=min(0,-18-bl) if bl is not None else None
    # Conservative bound on summed sample peaks, with 1 dB margin. Rendering still
    # needs true-peak measurement after EQ/time-stretch; source peaks are not enough.
    pa=a.get('signals',{}).get('sample_peak_dbfs');pb=b.get('signals',{}).get('sample_peak_dbfs')
    headroom=None
    if all(number(v) for v in (pa,pb,ga,gb)):
        bound=20*math.log10(10**((pa+ga)/20)+10**((pb+gb)/20))
        headroom=min(0,-1-bound);ga+=headroom;gb+=headroom
    else:issues.append(issue('peak_missing','缺少音频采样峰值，无法计算叠加余量'))
    events=[{'name':'B 音频启动','planned_sec':playback_start,'actual_sec':None,'source_b_sec':cue},
            {'name':'开始可听交接','planned_sec':entry,'actual_sec':None,'source_a_sec':entry*ra,'source_b_sec':b_at_entry}]
    if trigger:events.append({'name':'B 中频开始恢复','planned_sec':restore_start,'actual_sec':None})
    events.append({'name':'完成交接：A 静音 / B 释放','planned_sec':handoff,'actual_sec':None,'source_a_sec':a1,'source_b_sec':b1})
    for i,e in enumerate(events):e['event_id']=f'event_{i+1}'
    result.update(case=case,entry_sec=entry,handoff_sec=handoff,overlap_bars=count,target_bpm=target,
        mapping={'a':{'rate':ra,'source_bpm_local':abpm,'playback_start_sec':0,'source_cue_sec':0},
                 'b':{'rate':rb,'source_bpm_local':bbpm,'playback_start_sec':playback_start,'source_cue_sec':cue,
                      'source_at_entry_sec':b_at_entry,'source_at_handoff_sec':b1},
                 'formula':'B plan_sec = handoff_sec + (source_sec - B intro_end_sec) / B rate',
                 'max_beat_error_ms':round(max_error,3),'beat_error_tolerance_ms':50},
        eq={'b_mid_cut_db':-9 if trigger else 0 if trigger is False else None,'low_hz':250,'high_hz':4000,
            'restore_start_sec':restore_start,'restore_end_sec':handoff,'restore_to_db':0,
            'definition':'中频预设为实验参数；衰减整曲会同时影响该频带乐器，恢复曲线按 dB 线性'},
        gains={'a_trim_db':ga,'b_trim_db':gb,'a_lufs':al,'b_lufs':bl,'b_minus_a_lu':bl-al if bl is not None and al is not None else None,
               'extra_headroom_db':headroom,'fade':{'from_sec':entry,'to_sec':handoff,'a':[1,0],'b':[0,1],'curve':'linear_amplitude'},
               'measurement':'ungated 3s K-weighted window energy; -18 LUFS attenuation-only reference'},
        vocal_overlap={'rule_triggered':trigger,'a_intervals':a_overlap,'b_intervals':b_overlap,'simultaneous_intervals':simultaneous},events=events)
    result['status']='blocked' if any(x['severity']=='blocked' for x in issues) else 'needs_review' if issues else 'ready'
    result['id']=digest(result)
    return result
