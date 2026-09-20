#!/usr/bin/env python3
import csv,hashlib,html,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'outputs/hiphop-v3';OUT=BASE/'listen'
def h(x):return html.escape(str(x))
def clock(s):return f'{int(s)//60}:{s%60:05.2f}'
def table(headers,rows):return '<div class="table"><table><thead><tr>'+''.join('<th>'+h(v)+'</th>' for v in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+h(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def audio(src):return '<audio controls preload="metadata" src="'+h(src)+'"></audio>'
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2))

def main():
    global BASE, OUT
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,default=BASE);args=parser.parse_args()
    BASE=args.data_dir.resolve();OUT=BASE/'listen'
    p=json.loads((OUT/'plan.json').read_text());e=json.loads((OUT/'execution.json').read_text());audit=json.loads((BASE/'style-audit.json').read_text());selected={t['report_id'] for t in p['tracks']}
    seen=set();candidates=[];weak=[]
    for r in audit['rows']:
        if 'error' in r:continue
        key=r['audio'].get('catalog_track_id') or r['id']
        if key in seen:continue
        seen.add(key);top=r.get('model_top') or [];model=bool(top and top[0].get('parent')=='Hip Hop')
        manual=any(x['profile'].get('manual_primary_style')=='hiphop' for x in r.get('styles',[]))
        if not model and not manual:continue
        sections=r.get('sections') or {};songformer=isinstance(sections,dict) and sections.get('source')=='songformer';items=sections.get('items',[]) if isinstance(sections,dict) else sections
        intro=bool(items and items[0].get('label')=='intro');vocal=bool(r.get('vocal_keys'));chosen=r['id'] in selected
        if chosen:reason='本次选入：模型首选 Hip-Hop，有 SongFormer 前奏／副歌及绑定的人声区间'
        elif r['title']=='Come Up':reason='拍网格与标注 BPM 冲突超过 5%，排除'
        elif not songformer:reason='暂不选入：当前候选快照没有同等完整的 SongFormer 段落，或为旧式粗分段'
        elif not intro:reason='没有标为 intro 的开头，不补造前奏'
        elif r['title']=='DSK':reason='第一遍副歌候选仅约 3 秒，不适合本次衔接'
        else:reason='本次优先 125–149.4 BPM 且资料完整的 Trap／Grime 组合；保留为其他场次候选'
        candidates.append({'title':r['title'],'report_id':r['id'],'bpm':r['summary'].get('bpm'),'manual_hiphop':manual,'model_top1':top[0] if top else None,'songformer':songformer,'vocal_intervals_available':vocal,'selected':chosen,'reason':reason})
    selection={'scanned_audio_identity_records':audit['total'],'note':'音频身份记录含同曲不同版本，不等于歌曲数；候选表按目录歌曲 ID 去重。人工标签与模型结果分别保留。','unreadable_style_records':len([r for r in audit['rows'] if 'error' in r]),'candidate_count':len(candidates),'candidates':candidates,'selected_order':[t['title'] for t in p['tracks']],'selected_reason':p['selection'],'route':p['ranking']}
    save(OUT/'selection.json',selection)
    with (OUT/'hiphop-candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['歌曲','BPM','已有人工 Hip-Hop 标签','模型首选','原始模型分数','本次选入','理由'])
        for r in candidates:writer.writerow([r['title'],r['bpm'],r['manual_hiphop'],(r['model_top1'] or {}).get('label'),(r['model_top1'] or {}).get('score'),r['selected'],r['reason']])
    snapshots=OUT/'reports';snapshots.mkdir(exist_ok=True)
    for t in p['tracks']:shutil.copy2(BASE/'inputs/reports'/(t['report_id']+'.json'),snapshots/(t['report_id']+'.json'))
    shutil.copy2(ROOT/'mixing/report_assets/logo.png',OUT/'logo.png')
    css=(ROOT/'mixing/report_assets/review.css').read_text()
    css+=' .pill{background:#e8efe6;border-radius:5px;padding:4px 9px;display:inline-block;color:#28573d} .legend{font-size:13px;color:#596e60} .metrics{display:flex;flex-wrap:wrap;gap:24px;margin:22px 0}.metrics b{font-size:27px;color:#24543e} .metrics span{display:block;font-size:13px} input[type=search]{width:100%;padding:12px;border:1px solid #ccd6ce;border-radius:7px} .catalog tr[hidden]{display:none}'
    nav='<header><img src="logo.png" alt="HarBeat"><b>HarBeat / HIP-HOP × V3</b><a href="index.html">混音试听</a><a href="decision-log.html">接歌日志</a><a href="catalog.html">曲库筛选</a><a href="/analysis-lab-static/demo-3-20260920/index.html">已确认 V3 基线</a></header>'
    footer='<footer>音频处理沿用已确认的同事 V3 渲染函数。新歌曲没有同事参考成品，不作“音频复现一致”的声明。<br>风格分数是模型原始输出，不是准确率。段落、人声和部分拍网格仍待试听确认；没有回写 NAS 原始分析。</footer>'
    js='''<script>document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(b!==a)b.pause()})));const q=document.querySelector('#search');if(q)q.addEventListener('input',()=>document.querySelectorAll('.catalog tbody tr').forEach(tr=>tr.hidden=!tr.textContent.toLowerCase().includes(q.value.toLowerCase())));</script>'''
    def page(file,title,body):
        (OUT/file).write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+h(title)+'</title><style>'+css+'</style></head><body><main>'+nav+body+footer+'</main>'+js+'</body></html>')
    def timeline():
        total=e['duration_sec'];svg='<svg viewBox="0 0 900 270" role="img" aria-label="六首歌的播放及重叠时间"><rect width="900" height="270" fill="#f4f6f1"/>'
        for i,(t,x) in enumerate(zip(p['tracks'],e['tracks'])):
            start=0 if i==0 else next(z['render_timeline_sec'] for z in e['events'] if z['transition']==i and z['event']=='进歌')
            left=180+start/total*680;width=x['duration_sec']/total*680
            svg+=f'<text x="12" y="{38+i*35}" font-size="13" fill="#243b2e">{h(t["title"])}</text><rect x="{left:.2f}" y="{23+i*35}" width="{width:.2f}" height="22" rx="4" fill="{["#36654e","#668164"][i%2]}"/><text x="{left+5:.2f}" y="{38+i*35}" font-size="11" fill="white">{clock(start)}</text>'
        for sec in range(0,int(total)+1,30):svg+=f'<text x="{180+sec/total*680:.1f}" y="255" font-size="11" fill="#5c705f">{clock(sec)}</text>'
        return svg+'</svg>'
    body='<h1>Hip-Hop 六首 · V3 混音</h1><p>从 NAS 已分析曲库筛选，采用已确认的同事 V3 音量、变速和 EQ 处理。本次为 Trap／Grime 方向。</p><div class="metrics"><div><b>6 首</b><span>模型首选 Hip-Hop</span></div><div><b>'+clock(e['duration_sec'])+'</b><span>完整混音</span></div><div><b>5 次</b><span>人声中频避让</span></div></div>'
    body+='<article><h2>完整混音</h2>'+audio('HarBeat-HipHop-6-V3.mp3')+'<div class="links"><a download href="HarBeat-HipHop-6-V3.mp3">下载 MP3</a><a download href="HarBeat-HipHop-6-V3.wav">下载 WAV</a><a href="decision-log.html">查看完整接歌日志 →</a></div></article>'
    body+=timeline()+'<h2>本次六首歌</h2>'+table(['顺序','歌曲／艺人','BPM','模型细分候选','原始分数'],[[i+1,t['title']+' / '+(t['artist'] or ''),t['bpm'],t['style_evidence']['data']['top'][0]['label'],f"{t['style_evidence']['data']['top'][0]['score']:.4f}"] for i,t in enumerate(p['tracks'])])
    body+='<div class="note">保留主体原速，仅让下一首前奏匹配当前歌曲；本次所有进歌源位置均为 0。RATATA 前奏在上一首退出前加速约 14.3%，这是沿用 V3 局部速度匹配的结果，可重点试听第二次转场。</div><h2>五次转场单独试听</h2>'
    for i,t in enumerate(p['transitions']):body+=f'<article class="transition"><h3>{i+1:02d} · {h(t["from_title"])} → {h(t["to_title"])}</h3><p>重叠 {t["overlap_seconds"]:.2f} 秒 · B 前奏 {t["entry_rate"]:.6f} 倍速 · B 中频 −5 dB，最后半小节恢复</p>'+audio(f'transition-{i+1:02d}.mp3')+'</article>'
    body+='<h2>已保存的基线</h2><p>已确认的 Future Bass V3 保存在 NAS 的 mix-releases/v3-20260920-confirmed，并在本机另存完整版本包。此前试听页、声音和原始分析均保留。</p><a href="catalog.html">查看 NAS Hip-Hop 候选及本次筛选理由 →</a>'
    page('index.html','HarBeat · Hip-Hop 六首 V3',body)
    body='<h1>从哪些歌曲中选出这六首</h1><p>先看已有风格证据，再检查段落、人声区间和速度范围。共扫描 '+str(audit['total'])+' 份音频身份记录，部分为同曲不同版本；下表按目录歌曲 ID 去重后有 '+str(len(candidates))+' 首具有人工 Hip-Hop 标签或模型首选 Hip-Hop 的候选。</p><p>另有 5 份报告的风格模块失败或为空，未当作有效模型结果。没有把弱次选、舞种分数或其他风格标签自动等同于 Hip-Hop。</p><div class="links"><a download href="hiphop-candidates.csv">下载曲库清单 CSV</a><a download href="selection.json">下载完整筛选记录</a></div><h2>本次筛选</h2>'+table(['条件','处理'],[['风格','选中六首的 Discogs400 首选上级类别均为 Hip Hop；细分为 Trap／Grime'],['预处理','已有 SongFormer 前奏和第一遍副歌；人声记录核对曲目、分析运行 ID 与 vocals 文件哈希'],['速度','选定六首 125–149.4 BPM；不人为折半、翻倍或固定到统一 BPM'],['拍网格','使用 NAS 原始 bars_ms 对齐；Come Up 标注 146.3 BPM，网格中位小节间隔对应 160 BPM，排除'],['排歌','对六首穷举 720 顺序；沿用同事评分公式，排除缺少所需前奏网格或窗口无法容纳的转场，剩余 '+str(p['ranking']['valid'])+' 条可执行路线'],['旧曲库','保留经典 Hip-Hop 候选；本次优先资料完整的已发布分析，未把粗 drop 标签补造成已确认副歌']])
    body+='<h2>曲库候选</h2><input id="search" type="search" placeholder="搜索歌曲、风格或筛选原因" aria-label="搜索曲库"><div class="catalog">'+table(['歌曲','BPM','已有人工标签','模型首选／分数','本次决定'],[[r['title'],r['bpm'],'Hip-Hop' if r['manual_hiphop'] else '—',((r['model_top1']['label']+' / '+format(r['model_top1']['score'],'.4f')) if r['model_top1'] else '尚无模型结果'),r['reason']] for r in candidates])+'</div>'
    page('catalog.html','HarBeat · NAS Hip-Hop 筛选',body)
    body='<h1>Hip-Hop · 接歌决策与执行日志</h1><p>这份冻结计划驱动本次离线渲染。时间对照来自原渲染器测得的片段长度，不代表浏览器声卡实际播放时间。</p>'+audio('HarBeat-HipHop-6-V3.mp3')+timeline()
    body+='<h2>本次使用的预处理信息</h2>'+table(['信息','用途','来源'],[['风格细分类别及分数','筛选候选；与人工标签分开展示','extensions.genre / Discogs400'],['BPM、原始小节首拍','前奏速度匹配、选点与小节计数','core.analysis.tempo / beat_grid.bars_ms'],['连续前奏／第一遍副歌','截取播放范围，选择三种接歌情况','core.analysis.sections / SongFormer'],['人声起止时间','A、B 各自交接窗口的人声占比及中频避让','documents.vocal_activity / Silero，保留 needs_review'],['调性、鼓组','沿用同事排歌评分；鼓组降级标记保留','core.analysis.key / drum_groups'],['原曲及素材哈希','确认混音使用的是对应分析的真实文件','NAS manifest assets.master、vocals 及完整文件校验']])
    body+='<h2>音频处理参数</h2>'+table(['处理','本版参数'],[['B 进入','低频 −7 dB / 140 Hz；高频 +1.2 dB / 3600 Hz'],['人声冲突','本次全部触发 B 中频 −5 dB / 1200 Hz / Q 1.05'],['B 恢复','出歌点前半小节，将处理后的信号与原音线性交叉淡化'],['A 退出','尾段低频 −9 dB、高频 −1.4 dB；总音量线性退出'],['增益与限幅','每首 0.76；原版 limiter limit=0.96、level=false'],['结尾','最后一首 7 秒淡出'],['成品测量',f"{e['mp3_levels']['input_i']} LUFS；{e['mp3_levels']['input_tp']} dBTP；沿用 V3 处理，未另做响度归一化"]])
    body+='<h2>原段落与选点变化</h2>'+table(['歌曲','前奏结束','副歌开始 → 结束','小节数 前奏／副歌','对齐改动 ms 前奏／副歌起／止','拍点待复核'],[[t['title'],f"{t['intro']['end_ms']/1000:.3f}s",f"{t['chorus']['start_ms']/1000:.3f} → {t['chorus']['end_ms']/1000:.3f}s",f"{t['intro']['bars']} / {t['chorus']['bars']}",str(list(t['snap_changes_ms'].values())),'是' if t['tempo_quality'].get('needs_review') else '原模型未标记；仍未人工确认'] for t in p['tracks']])
    body+='<p>仅吸附到已记录的小节位置；不使用 V2 的直线拟合外推。部分前奏内没有原始小节线，因此需要前奏尾部定位的组合被排除。RATATA 的 9 小节副歌候选保持原样。</p>'
    for i,t in enumerate(p['transitions']):
        duration=t['overlap_seconds'];restore=1-t['restore_half_bar_seconds']/duration;rx=40+restore*720
        curve=f'<svg viewBox="0 0 820 185" role="img" aria-label="线性音量交接及最后半小节 EQ 恢复"><rect width="820" height="185" fill="#f4f6f1"/><path d="M40 28 L760 105" stroke="#a17342" stroke-width="3" fill="none"/><path d="M40 105 L760 28" stroke="#36654e" stroke-width="3" fill="none"/><path d="M40 150 L{rx:.1f} 150 L760 123" stroke="#486987" stroke-width="3" fill="none"/><text x="44" y="20" font-size="12">A 渐弱 / B 渐强</text><text x="44" y="175" font-size="12">B EQ：前段保持衰减，最后半小节恢复原音</text><text x="725" y="119" font-size="11">{duration:.2f}s</text></svg>'
        body+=f'<article class="transition"><h2>{i+1:02d} · {h(t["from_title"])} → {h(t["to_title"])}</h2><p>A 副歌 {t["a_chorus_bars"]} 小节，B 前奏 {t["b_intro_bars"]} 小节；按同事的对应接歌情况选择窗口。</p>'+curve
        body+=table(['选点与判断','记录'],[['接歌情况','前奏／副歌等长' if t['case'].startswith('case_1') else 'A 副歌较长，完整 B 前奏进入' if t['case'].startswith('case_2') else 'A 副歌较短，最后四小节'],['原曲窗口',f"A：{t['a_transition_start_ms']/1000:.3f}–{t['a_exit_ms']/1000:.3f}s；B：{t['b_entry_ms']/1000:.3f}–{t['b_intro_end_ms']/1000:.3f}s"],['B 速度映射',f"{p['tracks'][i]['bpm']} ÷ {p['tracks'][i+1]['bpm']} = {t['entry_rate']:.9f}；主体恢复原速"],['重叠与恢复',f"重叠 {duration:.6f}s；最后 {t['restore_half_bar_seconds']:.6f}s 恢复 B EQ"],['人声占比',f"A {t['a_vocal_ratio']:.1%} / B {t['b_vocal_ratio']:.1%}；触发中频避让"],['人声规则','原区间前后扩展 300ms；双方各自至少 500ms 且占窗口 5%。这是同事的双方窗口判定，不是 V2 的严格同时重叠判定。'],['排歌得分',f"{t['score']:.6f}（人为规则分，不是好听概率）"],['得分分项',json.dumps(t['score_components'],ensure_ascii=False)],['鼓组限制','沿用同事的鼓组相似度权重 0.17；源记录的降级信息保留，没有称其已校准']])
        body+=table(['事件','计划时间','渲染时长推算','差值 ms'],[[z['event'],clock(z['planned_sec']),clock(z['render_timeline_sec']),f"{z['difference_ms']:.3f}"] for z in e['events'] if z['transition']==i+1])
        body+='<p>表中时间按片段长度映射，EQ 内部分块的毫秒舍入、限幅器延迟尚未单独测量。</p>'+audio(f'transition-{i+1:02d}.mp3')+'</article>'
    body+='<h2>排歌与适配边界</h2><p>原同事脚本的选点、三种情况、人声规则和评分函数直接复用。缺失的 phrase_mix 小节吸附函数用“最近已记录小节线”适配；调性与鼓组辅助函数取自你此前提供的 HarBeat V4 包，并记录文件哈希。没有声称这些缺失依赖与同事环境完全相同。音频渲染仍使用已经过 V3 一致性验证的原函数。</p><p>穷举 720 种顺序，本批数据有 '+str(p['ranking']['valid'])+' 条满足窗口和原网格覆盖条件；缺失前奏小节位置时不补造定位。全部路线、原始得分和拒绝原因可下载。</p>'
    body+='<div class="links">'+''.join(f'<a download href="{f}">{label}</a>' for f,label in [('plan.json','冻结计划'),('execution.json','执行命令与测量'),('routes.json','720 条路线与拒绝原因'),('selection.json','筛选依据'),('artifact-checksums.json','文件校验清单')])+'</div><h2>六首原始分析快照</h2><div class="links">'+''.join(f'<a download href="reports/{t["report_id"]}.json">{h(t["title"])}</a>' for t in p['tracks'])+'</div>'
    page('decision-log.html','HarBeat · Hip-Hop V3 接歌日志',body)
    files=[x for x in OUT.rglob('*') if x.is_file() and x.name!='artifact-checksums.json'];save(OUT/'artifact-checksums.json',{str(x.relative_to(OUT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(files)})
    print('Built pages:',len(candidates),'catalog candidates;',len(files),'artifacts')
if __name__=='__main__':main()
