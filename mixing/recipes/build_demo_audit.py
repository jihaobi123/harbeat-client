#!/usr/bin/env python3
"""Reconstruct an evidence-backed decision report for an existing frozen render.
Does not replan, rerender, edit source reports, or claim retrospective wall-clock events.
"""
import argparse, hashlib, html, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from analysis_platform.report import validate_report, digest


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(x): return json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False)
def span(a,b): return f'{a:.3f}–{b:.3f} 秒'
def stamp(x): return f'{int(x)//60}:{x%60:06.3f}'
def n(x,places=3): return '未知' if x is None else f'{x:.{places}f}'

def intersect(rows, lo, hi):
    return [{'source_index':i,'original':v,'clipped':{'start':max(lo,v['start']),'end':min(hi,v['end'])}}
            for i,v in enumerate(rows or []) if min(hi,v['end'])>max(lo,v['start'])]

def loudness(c, lo, hi):
    rows=[{'source_index':i,**x} for i,x in enumerate(c['signals']['local_loudness']) if x['start']>=lo-.001 and x['end']<=hi+.001]
    value=10*math.log10(sum(10**(x['lufs']/10) for x in rows)/len(rows)) if rows else None
    return {'source_path':'extensions.dj_signals.data.local_loudness','window_selection':'only complete windows wholly within source overlap','source_range_sec':[lo,hi],'windows':rows,'aggregated_lufs':value}

class Report:
    def __init__(self): self.md=[];self.html=[]
    def heading(self,t,level=2):
        self.md.append('#'*level+' '+t);self.html.append(f'<h{level}>{html.escape(t)}</h{level}>')
    def text(self,t):
        self.md.append(t);self.html.append('<p>'+html.escape(t)+'</p>')
    def table(self,heads,rows):
        def escape(x):return str(x).replace('|','\\|').replace('\n',' ')
        self.md.append('\n'.join(['| '+' | '.join(map(escape,heads))+' |','| '+' | '.join(['---']*len(heads))+' |']+['| '+' | '.join(map(escape,r))+' |' for r in rows]))
        self.html.append('<div class="table"><table><thead><tr>'+''.join('<th>'+html.escape(str(x))+'</th>' for x in heads)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>')
    def raw(self,title,obj):
        self.md.append(f'<details><summary>{title}</summary>\n\n```json\n{dump(obj)}\n```\n\n</details>')
        self.html.append('<details><summary>'+html.escape(title)+'</summary><pre>'+html.escape(dump(obj))+'</pre></details>')
    def clip(self,file,number):
        self.md.append(f'[试听转场 {number}]({file})')
        self.html.append(f'<audio controls preload="none" src="{html.escape(file)}"></audio>')


def build(out,reports):
    plan=json.loads((out/'plan.json').read_text());execution=json.loads((out/'execution.json').read_text());contracts=json.loads((out/'contracts.json').read_text())
    if digest({k:v for k,v in plan.items() if k!='id'})!=plan['id']:raise ValueError('plan fingerprint mismatch')
    if len(contracts)!=len(plan['tracks']) or len(execution['tracks'])!=len(contracts):raise ValueError('track count mismatch')
    if sha(out/'HarBeat-DEMO-1.0-preview.wav')!=execution['wav_sha256']:raise ValueError('rendered audio fingerprint mismatch')
    audit={'schema':'harbeat.demo_decision_audit','version':'1.0','generated_at':datetime.now(timezone.utc).isoformat(),
           'record_kind':'post_render_reconstruction_from_frozen_evidence','plan_id':plan['id'],
           'input_artifacts':{k:sha(out/k) for k in ('plan.json','contracts.json','execution.json')},
           'wav_sha256':execution['wav_sha256'],'mp3_sha256':sha(out/'HarBeat-DEMO-1.0-preview.mp3'),
           'human_confirmed':False,'clock':'original audio seconds / pair-local seconds / set-global seconds / offline sample index; no browser telemetry',
           'tracks':[],'transitions':[]}
    r=Report();r.heading('HarBeat DEMO 1.0 · 选段与衔接详细日志',1)
    r.text(f'对应已生成的六首串烧，时长 {execution["duration_sec"]:.3f} 秒，目标 100 BPM。本文从冻结计划、六份预处理快照及实际渲染记录重建决策过程。本次只补日志，音频没有重新生成。日志生成时间为 {audit["generated_at"]}；这不是当时逐步采集的运行墙钟日志。')
    r.text('所有段落、拍网格和人声区间仍待试听确认。原始严格输入含阻塞项；本次试混另外生成候选网格和候选边界，再以显式 preview 模式执行。原报告未被覆盖。')
    r.heading('1. 本版如何理解你的规则')
    r.table(['环节','本次实际做法'],[
        ['播放顺序','按提供的六首曲库清单顺序；没有运行同风格筛选或最佳顺序搜索。'],
        ['播放范围','每首从原文件 0 秒解码至首个连续 chorus 段落结束候选；第 2–6 首在可听进歌点前保持静音。'],
        ['第一遍副歌','相邻、同名且首尾相差不超过 1 毫秒的模型分段合并为一个段落，取第一个 chorus；不按固定约 125 秒截取。'],
        ['速度','本版显式固定全套 100 BPM；各曲整段恒速保调变速，避免同一首前后两个转场使用不同速度。'],
        ['出歌点','B 前奏结束 / 第一主歌开始候选对齐 A 第一副歌结束候选。'],
        ['等长','重叠整个 B 前奏；本批未出现。'],
        ['A 副歌更长','重叠 A 副歌最后 B 前奏所需的小节；本批五次均为此情况。'],
        ['B 前奏更长','规则保留最后 4 小节交接，选 silent_preroll 策略；本批未触发，不能用本次试听证明该分支效果。'],
        ['人声规则','A 整个第一副歌与 B 整个前奏各自存在人声候选就触发；不是同时有人声才触发。'],
        ['处理方式','完整原曲线性音量交接 + B 250–4000 Hz 中频衰减；不做分轨重组，不做额外低频互换。'],
        ['EQ 参数','触发时 -9 dB 为试验预设，最后半小节（100 BPM、4/4 拍下 1.2 秒）按 dB 线性恢复至 0。'],
        ['时间验证','actual 为渲染器实际应用自动化的采样位置；不是重新识别输出鼓点，也不是浏览器播放回执。']])
    r.heading('2. 哪些预处理信息参与了这版混音')
    r.table(['数据','来源字段 / 算法','实际用途'],[
        ['原曲身份','audio.sha256、hash_verification；渲染前再次计算本地 MP3 SHA256','确保六份分析与实际播放原曲一一对应。'],
        ['段落','documents.core.analysis.sections；本批 pipeline.sections = songformer','挑选 intro / verse / 首个连续 chorus，保存原始标签和边界。'],
        ['拍号、拍点、小节首拍','timeline.beats / timeline.downbeats、core.analysis.beat_grid','原网格校验；候选适配器用已有小节拟合规则 4/4 网格，计算段落小节数和半小节。'],
        ['速度','原 tempo 留作对照；实际使用选定段落的小节数及端点计算局部 BPM','240 × 小节数 ÷ 段落秒数，rate = 100 ÷ 局部 BPM。'],
        ['分离人声与人声区间','htdemucs 分离人声；documents.vocal_activity，Silero VAD 候选','判定段落是否含人声、映射转场内的人声区间与交集。分离轨没有混入输出音频。'],
        ['局部响度','extensions.dj_signals.data.local_loudness；完整落入交接区间的 3 秒 K 加权无门限窗口','在线性能量域平均，再换回 dB；以 -18 为只衰减参考计算增益。不是最终输出 LUFS 归一化。'],
        ['采样峰值','extensions.dj_signals.data.sample_peak_dbfs','估算两曲叠加上界和额外余量；渲染后另测真峰值。'],
        ['小节 RMS、低中高频能量、人声占比','候选 contract.grid.bars 的附带测量','保留供诊断，本次没有据此改变选点或 EQ 频带。'],
        ['已就绪但不参与本次决策','风格、乐器、和弦、调性、情绪、粗糙度、重复段落、起音密度、动态范围、鼓子轨、旧 transition_windows','本次不据此选顺序、不做和声配对、不改 EQ、不决定窗口；数据存在不等于算法使用。']])
    r.text('候选网格计算采用 5 轮线性拟合：初始步长取原小节间隔中位数，剔除残差超过 max(100 毫秒, 3 × 残差绝对值中位数) 的点；至少保留 8 点、覆盖不少于 80%，最终内点最大残差不超过 100 毫秒。边界调整上限为半个小节加 50 毫秒；这只是本次候选准入规则，不是人工确认或模型准确率。')
    r.heading('3. 六首歌逐首选段依据')
    for i,(t,c,x) in enumerate(zip(plan['tracks'],contracts,execution['tracks'])):
        source=reports/(t['audio_sha256']+'.json');report=validate_report(json.loads(source.read_text()))
        if report['id']!=t['report_id'] or c['report_id']!=t['report_id']:raise ValueError('report identity mismatch')
        if digest({k:v for k,v in c.items() if k!='id'})!=c['id']:raise ValueError('contract fingerprint mismatch')
        core=report['documents']['core'];incoming=c['roles']['incoming'];outgoing=c['roles']['outgoing'];e=t['preview_estimation'];grid=c['grid']
        first_chorus=next(z for z in c['structure']['episodes'] if z['label']=='chorus')
        offset=x['offset_sample']/execution['sample_rate'];end=offset+x['rendered_frames']/execution['sample_rate']
        start_audible=0 if i==0 else execution['clips'][i-1]['entry_sec']
        item={'number':i+1,'title':t['title'],'audio_sha256':t['audio_sha256'],'report_id':report['id'],'contract_id':c['id'],
              'report_snapshot':{'filename':source.name,'sha256':sha(source)},'source_hashes':report['source_hashes'],'pipeline':core.get('pipeline'),
              'structure_source':c['structure']['source'],'source_segments':c['structure']['segments'],'first_chorus_episode':first_chorus,
              'original_tempo':core['analysis'].get('tempo'),'preview_estimation':e,'roles':c['roles'],
              'selected_grid':{k:grid[k] for k in ('source','numerator','denominator','bpm')},
              'selected_bars':[z for z in grid['bars'] if z['start']<t['end_sec']+.001],
              'source_downbeats_through_chorus':[v for v in report['timeline']['downbeats'] if v<=e['adjustments']['chorus_end']['original_sec']+3],
              'vocals':c['vocals'],'available_extensions':{k:v.get('status') for k,v in report['extensions'].items()},
              'render_execution':x,'source_decode_range_sec':[0,t['end_sec']],'set_decode_range_sec':[offset,end],
              'set_audible_entry_plan_sec':start_audible,'fixed_trim_db':x['trim_db']}
        audit['tracks'].append(item)
        r.heading(f'3.{i+1} {t["title"]}',3)
        r.text(f'结构来源 {c["structure"]["source"]}，来源流水线记录为 {core["pipeline"]["sections"]}。首个 chorus 由 {len(first_chorus["parts"])} 个连续模型分段合并，原始范围 {span(first_chorus["start"],first_chorus["end"])}。本次解码原曲 {span(0,t["end_sec"])}，保留至副歌结束候选。')
        r.table(['边界','原始识别 / 秒','试混候选 / 秒','调整 / 毫秒'],[[{'intro_start':'前奏开始','intro_end':'前奏结束','verse_start':'第一主歌开始','chorus_start':'第一副歌开始','chorus_end':'第一副歌结束'}[k],n(v['original_sec']),n(v['candidate_sec']),n(v['delta_ms'])] for k,v in e['adjustments'].items()])
        r.text(f'候选前奏 {incoming["bar_count"]} 小节；候选副歌 {outgoing["bar_count"]} 小节。小节编号以本版推算的首小节为 1，前奏编号 {incoming["bar_indices"]}，副歌编号 {outgoing["bar_indices"]}。不是人工确认的乐谱编号。')
        r.text(f'原记录首小节 {e["first_recorded_bar_sec"]:.3f} 秒，向前推算为 {e["first_bar_sec"]:.3f} 秒。使用副歌结束后 3 秒内的 {e["source_bars"]} 个原始小节首拍拟合，保留 {e["fit_bars"]} 个内点，内点最大残差 {e["max_inlier_residual_ms"]:.3f} 毫秒。这个残差描述拟合一致性，不等于真实鼓点误差。')
        r.text(f'原分析 BPM {n((core["analysis"].get("tempo") or {}).get("bpm"))}，拟合 BPM {e["bpm"]:.6f}；最终播放速率 {x["rate"]:.9f}×，整首固定增益 {x["trim_db"]:.3f} dB。原曲 0 秒放置在串烧 {stamp(offset)}，可听进入计划点 {stamp(start_audible)}，本曲在串烧 {stamp(end)} 结束。速率小于 1 为减速，大于 1 为加速。')
        r.text(f'解码／变速长度与目标相差 {x["decoder_length_delta_samples"]} 个采样（{1000*x["decoder_length_delta_samples"]/execution["sample_rate"]:+.3f} 毫秒）；按目标长度在尾部截去多余采样或补零，未平移整首曲目。尾部修正也应纳入听感检查。')
        r.raw('原始模型分段（按原曲秒数）',c['structure']['segments'])
        r.raw('原严格输入的问题，仍保留在证据里',e['original_issues'])
        r.raw('身份与预处理版本记录',{'audio_sha256':t['audio_sha256'],'report_id':report['id'],'contract_id':c['id'],'source_hashes':report['source_hashes'],'pipeline':core['pipeline'],'vocal_producer':c['vocals'].get('producer')})
    r.heading('4. 五次转场逐次决策与执行')
    for i,p in enumerate(plan['pairs']):
        a,b=contracts[i:i+2];xa,xb=execution['tracks'][i:i+2];clip=execution['clips'][i];ra=p['mapping']['a']['rate'];rb=p['mapping']['b']['rate'];origin=clip['entry_sec']-p['entry_sec'];entry_a=p['entry_sec']*ra;entry_b=p['mapping']['b']['source_at_entry_sec'];a1=a['roles']['outgoing']['end_sec'];b1=b['roles']['incoming']['end_sec'];sr=execution['sample_rate']
        if p['a_contract_id']!=a['id'] or p['b_contract_id']!=b['id']:raise ValueError('transition contract mismatch')
        if digest({k:v for k,v in p.items() if k!='id'})!=p['id']:raise ValueError('pair fingerprint mismatch')
        ae=loudness(a,entry_a,a1);be=loudness(b,entry_b,b1)
        for side,x in [('a',xa),('b',xb)]:
            if not math.isclose(x['rate'],p['mapping'][side]['rate'],abs_tol=1e-9):raise ValueError('planned/executed rate mismatch')
            if not math.isclose(x['trim_db'],p['gains'][side+'_trim_db'],abs_tol=1e-9):raise ValueError('planned/executed trim mismatch')
        for side,v in [('a',ae),('b',be)]:
            if not math.isclose(v['aggregated_lufs'],p['gains'][side+'_lufs'],abs_tol=1e-9):raise ValueError('loudness evidence does not reproduce decision')
        vocal_a=intersect(a['vocals']['intervals'],a['roles']['outgoing']['start_sec'],a1);vocal_b=intersect(b['vocals']['intervals'],b['roles']['incoming']['start_sec'],b1)
        if bool(vocal_a and vocal_b)!=p['vocal_overlap']['rule_triggered']:raise ValueError('vocal rule mismatch')
        rawtrims={side:min(0,-18-p['gains'][side+'_lufs'])+p['gains']['extra_headroom_db'] for side in ('a','b')}
        ev=[x for x in execution['events'] if x['pair']==i+1]
        selected_a=[v for v in a['grid']['bars'] if v['index'] in a['roles']['outgoing']['bar_indices']][-p['overlap_bars']:]
        selected_b=[v for v in b['grid']['bars'] if v['index'] in b['roles']['incoming']['bar_indices']][-p['overlap_bars']:]
        bars=[{'number':j+1,'a_bar_index':u['index'],'b_bar_index':v['index'],'a_source':[u['start'],u['end']], 'b_source':[v['start'],v['end']], 'global_plan':[origin+u['start']/ra,origin+u['end']/ra]} for j,(u,v) in enumerate(zip(selected_a,selected_b))]
        event={'number':i+1,'plan_id':p['id'],'a':p['a_title'],'b':p['b_title'],'case':p['case'],'a_chorus_bars':a['roles']['outgoing']['bar_count'],'b_intro_bars':b['roles']['incoming']['bar_count'],
               'overlap_bars':p['overlap_bars'],'a_source_overlap':[entry_a,a1],'b_source_overlap':[entry_b,b1],'a_global_origin_sec':origin,
               'mapping':p['mapping'],'overlap_bar_mapping':bars,'section_vocal_evidence':{'a':vocal_a,'b':vocal_b},
               'overlap_vocal_evidence':p['vocal_overlap'],'vocal_global_simultaneous_intervals':[{'start':origin+v['start'],'end':origin+v['end']} for v in p['vocal_overlap']['simultaneous_intervals']],
               'loudness_evidence':{'a':ae,'b':be},'sample_peak_evidence_dbfs':{'a':a['signals']['sample_peak_dbfs'],'b':b['signals']['sample_peak_dbfs']},
               'pair_trim_before_set_consistency_db':rawtrims,'final_gains':p['gains'],'eq':p['eq'],'events':ev,'plan_issues':p['issues']}
        audit['transitions'].append(event)
        r.heading(f'4.{i+1} {p["a_title"]} → {p["b_title"]}',3);r.clip(clip['file'],i+1)
        r.text(f'A 副歌 {event["a_chorus_bars"]} 小节，B 前奏 {event["b_intro_bars"]} 小节，所以走“A 副歌更长”分支。取 A 副歌最后 {p["overlap_bars"]} 小节，与 B 完整候选前奏重叠；重叠时长 {p["handoff_sec"]-p["entry_sec"]:.3f} 秒。A 副歌此前部分正常播放。')
        r.table(['动作','原曲 A / 秒','原曲 B / 秒','串烧计划时间'],[
            ['B 从文件头启动并静音','—','0.000',stamp(origin+p['mapping']['b']['playback_start_sec'])],
            ['开始可听交接',n(entry_a),n(entry_b),stamp(clip['entry_sec'])],
            ['开始恢复 B 中频' if p['eq']['b_mid_cut_db'] else '无需中频恢复',n(p['eq']['restore_start_sec']*ra),n(b1+(p['eq']['restore_start_sec']-p['handoff_sec'])*rb),stamp(origin+p['eq']['restore_start_sec']) if p['eq']['b_mid_cut_db'] else '未执行'],
            ['A 完全退出，B 达到固定增益',n(a1),n(b1),stamp(clip['handoff_sec'])]])
        r.text(f'A 局部 BPM {p["mapping"]["a"]["source_bpm_local"]:.6f}，rateA={ra:.9f}；B 局部 BPM {p["mapping"]["b"]["source_bpm_local"]:.6f}，rateB={rb:.9f}。原曲 B 的 s 秒映射为串烧 {origin:.9f} + {p["handoff_sec"]:.9f} + (s − {b1:.9f}) / {rb:.9f} 秒。相邻两次转场对同一首使用相同速率。')
        r.text(f'B 从文件头启动至进歌点静音 {p["entry_sec"]-p["mapping"]["b"]["playback_start_sec"]:.3f} 秒。进入时从原曲 {entry_b:.3f} 秒逐渐释出，所以“从文件头解码”不等于“文件头所有内容都可听”。')
        r.table(['重叠小节','A 候选小节号','A 原曲区间','B 候选小节号','B 原曲区间','串烧计划区间'],[[z['number'],z['a_bar_index'],span(*z['a_source']),z['b_bar_index'],span(*z['b_source']),f'{stamp(z["global_plan"][0])}–{stamp(z["global_plan"][1])}'] for z in bars])
        r.text(f'人声来源：A={a["vocals"]["source"]}，B={b["vocals"]["source"]}。A 完整副歌内命中 {len(vocal_a)} 段，B 完整前奏内命中 {len(vocal_b)} 段，因此段落级规则{ "触发" if p["vocal_overlap"]["rule_triggered"] else "不触发" }；转场内同时人声交集为 {len(p["vocal_overlap"]["simultaneous_intervals"])} 段。中频衰减 {p["eq"]["b_mid_cut_db"]} dB。')
        if p['vocal_overlap']['rule_triggered'] and not p['vocal_overlap']['simultaneous_intervals']:r.text('本次虽没有检测到转场内同时人声，仍按“两个完整段落各自有人声”的规则衰减 B。这是本版规则的直接结果，不能写成已确认发生双人声冲突。')
        rows=[]
        for side,key in [('A','a_intervals'),('B','b_intervals'),('同时','simultaneous_intervals')]:
            for v in p['vocal_overlap'][key]:rows.append([side,span(v['start'],v['end']),f'{stamp(origin+v["start"])}–{stamp(origin+v["end"])}'])
        r.table(['人声候选','转场局部时钟：A 播放从 0 开始','完整串烧时钟'],rows or [['—','未检测到','未检测到']])
        r.text(f'音量包络：u=clip((t−{p["entry_sec"]:.9f})/{p["handoff_sec"]-p["entry_sec"]:.9f},0,1)，A=(1−u)×10^({xa["trim_db"]:.6f}/20)，B=u×10^({xb["trim_db"]:.6f}/20)。这是线性振幅交接；“B 完全释出”指达到本曲固定增益，并非回到原文件 0 dB。')
        r.text('EQ 对完整 B 原曲的 250–4000 Hz 频带做互补 FIR 衰减（1025 taps），0 dB 时恢复为原信号。触发时最后 1.2 秒从 -9 dB 线性恢复至 0 dB；没有触发则不应用 EQ。频带中的乐器也会一起衰减。')
        r.table(['电平依据','A','B'],[
            ['原曲交接窗口',span(entry_a,a1),span(entry_b,b1)],
            ['完整 3 秒响度窗口个数',len(ae['windows']),len(be['windows'])],
            ['窗口能量平均 / LUFS',n(ae['aggregated_lufs']),n(be['aggregated_lufs'])],
            ['原曲采样峰值 / dBFS',n(a['signals']['sample_peak_dbfs']),n(b['signals']['sample_peak_dbfs'])],
            ['本对计算增益（含叠加余量）/ dB',n(rawtrims['a']),n(rawtrims['b'])],
            ['相邻转场统一后的整曲固定增益 / dB',n(xa['trim_db']),n(xb['trim_db'])]])
        r.text(f'本对额外叠加余量 {p["gains"]["extra_headroom_db"]:.3f} dB。每曲取其参与的两个转场中更低的增益，整首固定，因此这里最终增益可能比仅根据本次窗口计算的值更低。未采用动态压缩或逐段自动补偿；若听起来交接后偏小，需优先检查这一选择。')
        r.table(['执行动作','计划时间','实际采样位置对应时间','实际采样序号','差值 / 毫秒'],[[v['name'],stamp(v['planned_sec']),stamp(v['actual_sec']),v['actual_sample'],f'{v["delta_ms"]:+.6f}'] for v in ev])
        r.text(f'候选网格内部对齐最大偏差 {p["mapping"]["max_beat_error_ms"]:.3f} 毫秒，允许阈值 50 毫秒。规则网格经同一目标 BPM 映射后接近 0 是数学一致性结果，不能证明原录音里的鼓点、主歌或副歌真的对齐。')
        r.raw('人声判断原始区间及响度窗口索引',{'section_vocals':event['section_vocal_evidence'],'loudness_windows':event['loudness_evidence']})
    r.heading('5. 渲染、测量与证据边界')
    r.text('输出：44.1 kHz 双声道，WAV 为 24-bit，MP3 为 256 kbps。整段使用 FFmpeg atempo 保调变速；六段按固定位置叠加。首曲加入 5 毫秒起始淡入，末曲末尾 20 毫秒淡出以降低文件边缘突变。')
    r.table(['检查','记录'],[['WAV 综合响度',execution['levels_after']['input_i']+' LUFS'],['WAV 真峰值',execution['levels_after']['input_tp']+' dBTP'],['MP3 综合响度',execution['mp3_levels']['input_i']+' LUFS'],['MP3 真峰值',execution['mp3_levels']['input_tp']+' dBTP'],['渲染后全局额外衰减',str(execution['global_attenuation_db'])+' dB'],['最大离线事件时间偏差',f'{max(abs(v["delta_ms"]) for v in execution["events"]):.6f} ms'],['计划 ID',plan['id']],['WAV SHA256',execution['wav_sha256']]])
    r.text('响度工具运行在测量流程中；execution.json 里 levels_after/input_i 与 input_tp 才是成品测得值。其 output_i / output_tp 属于滤镜测量流程的假定输出，本次没有按这些 output 字段把整首标准化。')
    r.text('冻结计划中 execution.status=not_run、events.actual_sec=null 保留规划时状态。真实离线执行记录在 execution.json；本报告把两者关联起来，没有回写或篡改旧计划。')
    r.heading('6. 接歌失败时如何沿日志排查')
    r.table(['听到的现象','先核对的证据','能得出的结论边界'],[
        ['第一遍副歌截错 / 主歌进入太早','第 3 节原始段落、合并分段、边界吸附增量','原识别和候选吸附分别可能出错，需对原曲试听确认。'],
        ['落拍不齐 / 小节数奇怪','原首小节、拟合网格、原 BPM 与拟合 BPM、逐小节映射','例如候选 30 / 11 小节仍只是输入结果，不代表常见 8/16 小节乐句已人工确认。'],
        ['曲中鼓点漂移或变速伪影','固定 rate、拟合残差、解码长度修正','采样执行准确仍可能有恒速模型不适配或 atempo 瞬态伪影。'],
        ['B 人声被不必要压低 / 仍有人声冲突','完整段落人声命中、转场交集、EQ 触发规则','区分段落规则过宽、VAD 漏检、250–4000 Hz 衰减不足。'],
        ['交接后声音偏小','原始局部响度、本对增益、相邻转场取最小值后的固定增益','当前固定电平策略可能保守；不是播放器延迟。'],
        ['网页卡住或播放不及时','需要另采浏览器缓冲、播放时钟和事件回执','现有离线日志不能诊断浏览器实际播放延迟。']])
    r.text('下一次若修改识别边界、网格、目标 BPM 或自动化，应生成新的 plan ID 与新音频，再保存对应日志。不要让旧音频配上修改后的计划。')
    audit['limitations']=execution['limitations'];audit['output_levels']={k:execution[k] for k in ('levels_after','mp3_levels','global_attenuation_db')}
    (out/'decision-log.json').write_text(dump(audit));(out/'decision-log.md').write_text('\n\n'.join(r.md)+'\n')
    style='''body{margin:0;background:#f6f5f1;color:#172421;font:15px/1.7 system-ui,-apple-system,sans-serif}main{max-width:1120px;margin:auto;padding:28px 24px 70px}header{display:flex;gap:16px;flex-wrap:wrap;align-items:center;border-bottom:1px solid #d3dad3;padding-bottom:16px}header img{width:32px;height:32px;object-fit:contain}a{color:#205d49}h1{font-size:34px;line-height:1.3}h2{margin-top:46px;border-top:1px solid #d3dad3;padding-top:24px}h3{margin-top:36px;font-size:23px}p{max-width:1000px}.table{overflow:auto;background:white;border:1px solid #dfe2da;border-radius:8px;margin:18px 0}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;vertical-align:top;padding:10px 12px;border-bottom:1px solid #e7eae3;min-width:100px;overflow-wrap:anywhere}th{background:#edf1ea}details{padding:10px 14px;background:#eef1eb;margin:10px 0;border-radius:8px}summary{cursor:pointer}pre{font-size:12px;max-height:440px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}audio{width:min(100%,600px)}@media(max-width:600px){main{padding:18px 14px}h1{font-size:27px}h3{font-size:20px}th,td{min-width:130px}}'''
    head='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HarBeat · 详细混音日志</title><style>'+style+'</style><main><header><img src="logo.png" alt="HarBeat"><b>HarBeat / 决策与执行记录</b><a href="index.html">返回试听</a><a href="decision-log.md" download>下载完整文字日志</a><a href="decision-log.json" download>下载结构化证据</a><a href="decision-evidence.zip" download>下载分析快照与日志包</a></header>'
    (out/'decision-log.html').write_text(head+''.join(r.html)+'</main><script>document.querySelectorAll("audio").forEach(a=>a.addEventListener("play",()=>document.querySelectorAll("audio").forEach(b=>{if(a!==b)b.pause()})))</script></html>')
    return audit

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--reports',type=Path,required=True);a=p.parse_args();result=build(a.output,a.reports);print(f'Validated {len(result["tracks"])} tracks and {len(result["transitions"])} transitions; wrote decision log.')
