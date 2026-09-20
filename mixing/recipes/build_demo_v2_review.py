#!/usr/bin/env python3
"""Publish-only artifacts for V2 preview and unresolved-boundary listening review."""
from pathlib import Path
import json,html,sys,subprocess,hashlib
import numpy as np
import soundfile as sf
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/demo-render-v2/listen'

def esc(x):return html.escape(str(x))
def num(v):return '未知' if v is None else f'{v:.3f}'
def stamp(v):return f'{int(v)//60}:{v%60:06.3f}'
def table(head,rows):return '<div class="table"><table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def save_page(name,title,body,script=''):
    css='''*{box-sizing:border-box}body{margin:0;background:#f6f5f1;color:#172421;font:15px/1.7 system-ui,-apple-system,sans-serif}main{max-width:1160px;margin:auto;padding:28px 24px 70px}header{display:flex;flex-wrap:wrap;align-items:center;gap:16px;border-bottom:1px solid #d8dfd6;padding-bottom:18px}header img{width:34px;height:34px;object-fit:contain}a{color:#206348}h1{font-size:38px;line-height:1.2}h2{font-size:24px;margin-top:36px}h3{font-size:19px}p{color:#4c6056}.hero,article{background:white;padding:24px;border:1px solid #dce3d9;border-radius:12px;margin:18px 0}.note{background:#f1e8d6;padding:16px;border-left:3px solid #ab8643;margin:20px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.grid article{margin:0}.table{overflow:auto;margin:18px 0}table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #dce3d9;min-width:90px;overflow-wrap:anywhere}th{background:#eef2eb}.links{display:flex;gap:12px;flex-wrap:wrap;align-items:center}button,select,input{font:inherit}button{cursor:pointer;background:#edf3eb;border:1px solid #c4d4c8;padding:7px 12px;border-radius:6px;color:#24543e}input[type=number]{width:120px;padding:6px;border:1px solid #ccd6ce;border-radius:5px}input[type=checkbox]{width:18px;height:18px}label{display:inline-flex;gap:6px;align-items:center;margin:5px}audio{width:100%;margin-top:12px}small{color:#61796b}details{margin:16px 0}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:340px;overflow:auto;background:#eef2eb;padding:12px;font-size:12px}svg{width:100%;height:auto}footer{margin-top:40px;color:#748378;font-size:12px;overflow-wrap:anywhere}@media(max-width:720px){main{padding:18px 14px}.grid{grid-template-columns:1fr}h1{font-size:29px}article,.hero{padding:18px}td,th{min-width:115px}}'''
    header='<header><img src="logo.png" alt="HarBeat"><b>HarBeat / DEMO V2</b><a href="index.html">新版试听</a><a href="calibration-review.html">段落与小节核验</a><a href="decision-log.html">接歌决策日志</a><a href="/analysis-lab-static/demo-1-20260919/index.html">保留的 V1</a><a href="/analysis-lab">分析平台</a></header>'
    common='document.querySelectorAll("audio").forEach(a=>a.addEventListener("play",()=>document.querySelectorAll("audio").forEach(b=>{if(a!==b)b.pause()})));'
    (OUT/name).write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+css+'</style><main>'+header+body+'</main><script>'+common+script+'</script></html>')

def snippet_set(index,kind,source,a,b,platform_beats,bpm):
    prefix=f'review/{index+1:02d}-{kind}';paths={k:prefix+'-'+k+'.mp3' for k in ('dry','platform','colleague')}
    lo=max(0,min(a,b)-6);hi=max(a,b)+8
    if all((OUT/path).exists() for path in paths.values()):return {'start':lo,'end':hi,'files':paths}
    # Source decoded once by caller. All variants share identical source samples and level.
    audio,sr=source;piece=audio[round(lo*sr):round(hi*sr)].copy();gain=min(.5,.8/max(float(np.max(np.abs(piece))),1e-8));piece*=gain
    for variant,path in paths.items():
        x=piece.copy()
        if variant=='platform':ticks=[(v,k%4==0) for k,v in enumerate(platform_beats) if lo<=v<hi]
        elif variant=='colleague':
            step=60/bpm;indices=range(int(np.floor((lo-b)/step)),int(np.ceil((hi-b)/step))+1);ticks=[(b+k*step,k%4==0) for k in indices if lo<=b+k*step<hi]
        else:ticks=[]
        for t,accent in ticks:
            pos=round((t-lo)*sr);length=min(round(.025*sr),len(x)-pos)
            if length<=0:continue
            time=np.arange(length)/sr;click=(.07 if accent else .035)*np.sin(2*np.pi*(1600 if accent else 1100)*time)*np.exp(-time*180)
            x[pos:pos+length]+=click[:,None]
        target=OUT/path;target.parent.mkdir(exist_ok=True);wav=target.with_suffix('.wav');sf.write(wav,x,sr,subtype='PCM_24')
        subprocess.run(['ffmpeg','-y','-v','error','-i',str(wav),'-c:a','libmp3lame','-b:a','128k',str(target)],check=True,capture_output=True)
        wav.unlink()
    return {'start':lo,'end':hi,'files':paths,'original_level_gain':gain,'reference_clicks_are_candidates':True}

def chart(f,a,b,lo,hi):
    W=900;H=150;x=lambda t:45+(t-lo)/(hi-lo)*(W-65)
    times=np.asarray(f['novelty_times']);values=np.asarray(f['novelty']);sel=(times>=lo)&(times<=hi);v=values[sel];scale=max(float(np.max(v)),.01) if len(v) else 1
    path=' '.join(f'{x(t):.1f},{125-y/scale*80:.1f}' for t,y in zip(times[sel],v))
    marks=''.join(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="128" y2="140" stroke="#9aa69f"/>' for t in f['onsets'] if lo<=t<=hi)
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="附近声学变化和两版候选边界"><polyline points="{path}" fill="none" stroke="#92aa99" stroke-width="2"/>{marks}<line x1="{x(a)}" x2="{x(a)}" y1="40" y2="140" stroke="#157852" stroke-width="2"/><line x1="{x(b)}" x2="{x(b)}" y1="40" y2="140" stroke="#c18435" stroke-dasharray="4 3"/><text x="45" y="20" font-size="14" fill="#157852">平台 {a:.3f}s</text><text x="240" y="20" font-size="14" fill="#a26828">同事 {b:.3f}s</text><text x="450" y="20" font-size="13" fill="#657b6b">曲线：声音变化 · 短线：瞬态候选</text><text x="45" y="149" font-size="10">{lo:.2f}s</text><text x="{W-55}" y="149" font-size="10">{hi:.2f}s</text></svg>'

def main():
    plan=json.loads((OUT/'plan.json').read_text());execution=json.loads((OUT/'execution.json').read_text());cal=json.loads((OUT/'calibration.json').read_text());routes=json.loads((OUT/'routes.json').read_text())
    old=json.loads((ROOT/'outputs/demo-render-v1/listen/plan.json').read_text());contracts=json.loads((OUT/'contracts.json').read_text());other=json.loads((ROOT/'outputs/colleague-demo-review-20260920/mix_plan.json').read_text())
    import shutil
    shutil.copy2(ROOT/'web/src/analysis/assets/harbeat-logo.png',OUT/'logo.png')
    duration=execution['duration_sec'];levels=execution['mp3_levels'];body=f'<div class="hero"><small>EXHAUSTIVE ORDER · WINDOW VOCALS · LOW EQ</small><h1>DEMO V2 · 融合试混</h1><p>六首 · {duration:.2f} 秒 · 全程 100 BPM · 五次转场</p><audio controls preload="metadata" src="HarBeat-DEMO-2.0-preview.mp3"></audio><div class="links"><a href="HarBeat-DEMO-2.0-preview.mp3" download>下载 V2 MP3</a><a href="calibration-review.html">核验段落与小节</a><a href="decision-log.html">查看完整决策依据</a></div></div>'
    body+='<div class="note"><b>本版是带核验记录的试混，尚未人工验收。</b><br>排歌、人声与低频策略已整合；段落标签和小节相位仍待试听确认。声学对照支持 Clear、What Lovers Do 保留平台网格；另外四首不足以区分。没有把 30／11 小节自动改成 32／16，也没有覆盖 V1。</div>'
    body+='<h2>本版播放顺序</h2>'+table(['顺序','歌曲','原曲结束候选','播放速率','固定增益'],[[i+1,t['title'],f'{t["end_sec"]:.3f}s',f'{execution["tracks"][i]["rate"]:.6f}×',f'{execution["tracks"][i]["trim_db"]:.2f} dB'] for i,t in enumerate(plan['tracks'])])
    body+='<h2>五次转场</h2><div class="grid">'
    for x in execution['clips']:
        body+=f'<article><small>TRANSITION {x["number"]:02d}</small><h3>{esc(x["a"])} → {esc(x["b"])}</h3><p>{stamp(x["entry_sec"])} → {stamp(x["handoff_sec"])} · {x["overlap_bars"]} 小节<br>B 低频 −7 dB 后恢复 · A 低频渐降至 −9 dB<br>B 中频 {x["mid_cut_db"]} dB</p><audio controls preload="none" src="{x["file"]}"></audio></article>'
    body+='</div><h2>与两版方案的关系</h2>'+table(['能力','V2 采用方式'],[['自动排歌',f'穷举 {routes["permutations_considered"]} 种顺序，规则评分排序；不把分数当好听概率。'],['人声','只检查实际交接窗口，双方达到时长／占比门槛，并要求变速映射后持续交集；本次五次均未达到中频衰减触发门槛。'],['低频','完整原曲上只衰减：B 前奏 −7 dB，最后半小节恢复；A 低频在交接中逐渐降至 −9 dB。'],['时间与日志','同一份冻结计划驱动音量、低频与中频；记录实际应用采样位置。'],['校准','原音频瞬态对照与附近声学变化；无法证实标签时保留待确认，不从共同模型结果推断正确。']])
    body+=f'<footer>MP3 实测 {levels["input_i"]} LUFS · 真峰值 {levels["input_tp"]} dBTP。两版盲听需要先匹配响度；本版离线时钟记录不能证明浏览器播放延迟或音乐语义准确。</footer>'
    save_page('index.html','HarBeat · DEMO V2 试听',body)
    review='<h1>段落与小节：先核验，再确认</h1><p>这是原曲声学证据和候选拍点的试听页。所有确认初始为空；编辑只保存在当前浏览器，导出后才可作为下一版输入审查，不会直接改服务器分析。</p><div class="note">绿色是平台候选，橙色是同事交付边界。点拍音轨在同一原声片段上叠加候选拍点；强点代表该候选的小节首拍，不能当作已知正确答案。声音变化峰值只能提示“这里可能换了内容”，不能证明它叫主歌或副歌。</div><div class="links"><button id="export">导出人工核验记录 JSON</button><span id="saved" role="status">尚未保存人工确认</span><a href="calibration.json" download>下载声学对照数据</a></div>'
    review+=table(['歌曲','前奏瞬态接近率：平台 / 同事','副歌瞬态接近率：平台 / 同事','时间证据结论'],[[x['title'],*[f'{100*x["grid_comparison"]["role_comparisons"][role]["platform"]["coverage_50ms"]:.1f}% / {100*x["grid_comparison"]["role_comparisons"][role]["colleague"]["coverage_50ms"]:.1f}%' for role in ('incoming','outgoing')], '平台证据较强；仍待确认' if x['grid_comparison']['winner']=='platform' else '不足以区分'] for x in cal['tracks']])
    review+='<p>“瞬态接近率”指候选拍点附近 50 毫秒内有检测到的瞬态，不是准确率；休止、切分和非鼓声也会影响它。对照使用同事交付 BPM 与对应段落结束点重建恒速网格，其原 snap_to_bar 实现未包含在交付包中。各段至少 16 个候选点、接近率优势至少 8 个百分点且平均截断距离改善至少 10 毫秒，才标为时间证据较强。</p>'
    index_data=[];review_assets=[]
    for i,item in enumerate(cal['tracks']):
        track=next(t for t in old['tracks'] if t['title']==item['title']);contract=next(c for c in contracts if c['title']==item['title']);peer=next(t for t in other['tracks'] if t['title']==item['title'])
        r=json.loads((ROOT/'outputs/demo-render-v1/reports'/(track['audio_sha256']+'.json')).read_text());source=None
        review+=f'<article><h2>{i+1:02d} · {esc(item["title"])}</h2><p>候选第一副歌 {item["candidate_chorus_bars"]} 小节。原小节记录从 {item["source_first_downbeat_sec"]:.3f} 秒开始，平台向前推算到 {item["candidate_first_downbeat_sec"]:.3f} 秒；前奏首拍仍需要听。</p>'
        if item['unusual_phrase_length']:review+='<div class="note">这个小节长度不是本页预设的常见长度，仅提示复核，不据此改短或补长。</div>'
        assets=[]
        for b in item['boundaries']:
            kind=b['name'];a=b['platform']['time_sec'];other_time=b['colleague']['time_sec'];label={'intro_end':'前奏结束 / 主歌开始','chorus_start':'第一副歌开始','chorus_end':'第一副歌结束'}[kind]
            prefix=f'review/{i+1:02d}-{kind}'
            if not all((OUT/(prefix+'-'+v+'.mp3')).exists() for v in ('dry','platform','colleague')) and source is None:
                audio,sr=sf.read(track['path'],dtype='float32',always_2d=True);source=(audio,sr)
            clips=snippet_set(i,kind,source,a,other_time,contract['grid']['beats'],peer['bpm']);assets.append({'boundary':kind,**clips})
            ident=f'clip-{i}-{kind}'
            review+=f'<h3>{label}</h3>'+chart(item['features'],a,other_time,clips['start'],clips['end'])
            review+=f'<p>候选差 {b["delta_ms"]:+.1f} 毫秒；原声片段 {clips["start"]:.3f}–{clips["end"]:.3f} 秒。下面播放器从片段开头计时。</p><audio id="{ident}" controls preload="none" src="{clips["files"]["dry"]}"></audio><div class="links">'
            for variant,text in [('dry','原声'),('platform','平台候选点拍'),('colleague','同事候选点拍')]:review+=f'<button class="variant" data-player="{ident}" data-src="{clips["files"][variant]}">{text}</button>'
            review+='</div><p>附近声音变化峰候选：'+('、'.join(f'{v["time_sec"]:.3f}s' for v in b['nearby_acoustic_changes']) or '没有明显局部峰')+'。这些位置未自动写回边界。</p>'
            review+=f'<label>{label}：<input type="number" min="0" max="{contract["duration"]}" step="0.001" data-track="{i}" data-field="{kind}" value="{a:.6f}"> 秒</label>'
        review+=f'<p><label>首小节时间：<input type="number" min="0" step="0.001" data-track="{i}" data-field="first_downbeat" value="{contract["preview_estimation"]["first_bar_sec"]:.6f}"> 秒</label><label>BPM：<input type="number" min="40" max="240" step="0.001" data-track="{i}" data-field="bpm" value="{contract["preview_estimation"]["bpm"]:.6f}"></label></p><p><label><input type="checkbox" data-track="{i}" data-field="structure_confirmed">我已试听确认这三个段落边界</label><label><input type="checkbox" data-track="{i}" data-field="grid_confirmed">我已逐段核对首拍与小节</label></p>'
        review+='<details><summary>原模型段落与本次候选调整</summary>'+table(['标签','原始开始','原始结束'],[[z['label'],num(z['start']),num(z['end'])] for z in contract['structure']['segments'] if z['start']<track['end_sec']+8])+table(['锚点','原识别秒','试混候选秒','调整毫秒'],[[k,num(v['original_sec']),num(v['candidate_sec']),num(v['delta_ms'])] for k,v in track['preview_estimation']['adjustments'].items()])+'</details></article>'
        index_data.append({'title':item['title'],'audio_sha256':track['audio_sha256'],'report_id':contract['report_id'],'source_fingerprint':contract['source_fingerprint'],'duration_sec':contract['duration']})
        review_assets.append({'title':item['title'],'audio_sha256':track['audio_sha256'],'clips':assets})
        print('review clips ready:',item['title'],flush=True)
    (OUT/'review-clips.json').write_text(json.dumps(review_assets,ensure_ascii=False,indent=2))
    review+='<footer>参考：<a href="https://www.audiolabs-erlangen.de/resources/MIR/FMP/C4/C4S4_NoveltySegmentation.html">FMP 音乐结构新颖度分析</a>。本页实现为相邻 log-mel 特征变化诊断，不是论文算法的准确率复现，也不是新的段落分类模型。</footer>'
    js='const planId='+json.dumps(plan['id'])+';const tracks='+json.dumps(index_data,ensure_ascii=False)+';'+'''
const storageKey='harbeat-demo-v2-review:'+planId;const inputs=[...document.querySelectorAll('input[data-track]')];
try{const cached=JSON.parse(localStorage.getItem(storageKey)||'{}');inputs.forEach(x=>{const v=cached[x.dataset.track+':'+x.dataset.field];if(v!==undefined){if(x.type==='checkbox')x.checked=v;else x.value=v}})}catch(e){}
function save(){const values={};inputs.forEach(x=>values[x.dataset.track+':'+x.dataset.field]=x.type==='checkbox'?x.checked:x.value);try{localStorage.setItem(storageKey,JSON.stringify(values));document.getElementById('saved').textContent='已保存在当前浏览器，尚未提交到服务器'}catch(e){document.getElementById('saved').textContent='浏览器未允许保存，请导出记录'}}inputs.forEach(x=>x.addEventListener('change',save));
document.getElementById('export').onclick=()=>{const data=tracks.map((t,i)=>{const row={...t,structure_confirmed:false,grid_confirmed:false};inputs.filter(x=>Number(x.dataset.track)===i).forEach(x=>row[x.dataset.field]=x.type==='checkbox'?x.checked:Number(x.value));return row});const bad=data.find(t=>![t.intro_end,t.chorus_start,t.chorus_end,t.first_downbeat,t.bpm].every(Number.isFinite)||!(0<=t.first_downbeat&&t.first_downbeat<t.intro_end&&t.intro_end<=t.chorus_start&&t.chorus_start<t.chorus_end&&t.chorus_end<=t.duration_sec&&t.bpm>=40&&t.bpm<=240));if(bad){document.getElementById('saved').textContent='请检查 '+bad.title+' 的边界顺序与 BPM';return}const content={schema:'harbeat.demo_manual_review_export',plan_id:planId,exported_at:new Date().toISOString(),applied_to_server:false,tracks:data};const url=URL.createObjectURL(new Blob([JSON.stringify(content,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='demo-v2-manual-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
document.querySelectorAll('.variant').forEach(button=>button.onclick=()=>{const a=document.getElementById(button.dataset.player);a.pause();a.src=button.dataset.src;a.load();a.play().catch(()=>{});button.parentNode.querySelectorAll('button').forEach(b=>b.style.fontWeight=b===button?'700':'400')});
'''
    save_page('calibration-review.html','HarBeat · 段落与小节核验',review,js)
    log='<h1>DEMO V2 · 决策与执行日志</h1><p>同一份冻结计划生成音频和以下记录。运行状态是 rendered_preview；没有人工验收结论。</p><div class="links">'+''.join(f'<a href="{name}.json" download>{title}</a>' for name,title in [('plan','冻结计划'),('execution','实际采样执行'),('routes','720 路线与评分'),('calibration','声学校准对照'),('review-clips','核验片段索引')])+'</div>'
    log+='<h2>排歌依据</h2><p>所有歌曲仍使用 100 BPM。评分 = 1 − 2.6×|log2(A局部BPM/B局部BPM)| − 情况代价 − 人声交集代价 + 调性加分 + 可信鼓组加分。情况代价：等长0、A更长0.08、B更长0.18；人声交集代价 = 2×交集时长/交接时长，达到中频触发门槛再加0.18。调性按 Camelot 规则小幅加分。当前六首鼓组含降级结果，鼓组权重为0。没有以风格模型分数决定这六首是否属于同风格。</p>'
    log+=table(['排名','路线','规则分数'],[[i+1,' → '.join(routes['input_order'][j] for j in r['order']),f'{r["score"]:.6f}'] for i,r in enumerate(routes['ranking'][:10])])
    log+='<h2>选段与校准</h2><p>每首保留原文件开头至首个连续 chorus 结束。相邻同名模型段落合并；前奏结束必须接第一主歌。候选小节沿用已记录的规则网格及原始调整量；所有角色仍为 needs_review。详情和人工记录入口见校准页。B 在进歌点前静音预播放，末曲使用20毫秒尾部淡出。</p>'
    log+=table(['歌曲','前奏小节','第一副歌小节','段落语义结论'],[[c['title'],c['roles']['incoming']['bar_count'],c['roles']['outgoing']['bar_count'],'无独立标注，待试听确认'] for c in contracts])
    for i,p in enumerate(plan['pairs']):
        e=execution['clips'][i];v=p['vocal_decision_v2'];g=p['gains'];origin=e['entry_sec']-p['entry_sec']
        log+=f'<article><h2>{i+1}. {esc(p["a_title"])} → {esc(p["b_title"])}</h2><p>A 副歌更长，重叠 A 最后 {p["overlap_bars"]} 小节与 B 前奏。串烧 {stamp(e["entry_sec"])} 开始交接，{stamp(e["handoff_sec"])} 完成交接。</p>'
        log+=table(['映射','A','B'],[['局部 BPM',num(p['mapping']['a']['source_bpm_local']),num(p['mapping']['b']['source_bpm_local'])],['播放速率',f'{p["mapping"]["a"]["rate"]:.9f}',f'{p["mapping"]["b"]["rate"]:.9f}'],['原曲交接起点 / 秒',num(p['entry_sec']*p['mapping']['a']['rate']),num(p['mapping']['b']['source_at_entry_sec'])],['原曲交接终点 / 秒',num(p['handoff_sec']*p['mapping']['a']['rate']),num(p['mapping']['b']['source_at_handoff_sec'])],['交接区响度 / LUFS',num(g['a_lufs']),num(g['b_lufs'])],['本对增益 / dB',num(g['pair_trims_before_set_consistency']['a']),num(g['pair_trims_before_set_consistency']['b'])],['最终固定增益 / dB',num(g['a_trim_db']),num(g['b_trim_db'])]])
        log+=f'<p>整首固定增益取相邻转场中较低值。交接振幅 u 从0线性变到1：A=(1−u)×固定增益，B=u×固定增益；交接完成并不把 B 放大回原曲电平。B 低频先−7 dB，串烧 {stamp(origin+p["low_eq"]["b_restore_start_sec"])} 开始恢复，至交接结束为0 dB；A 低频在交接期间从0降至−9 dB。低频滤波分界140 Hz，2049 taps互补FIR；没有高频提升。</p>'
        log+=f'<p>人声区间先映射到播放时钟，再向两侧各扩0.3秒，只截取交接窗口。A 活动 {v["a_active_sec"]:.3f}s（{v["a_ratio"]*100:.1f}%），B 活动 {v["b_active_sec"]:.3f}s（{v["b_ratio"]*100:.1f}%）；原始交集 {v["raw_simultaneous_sec"]:.3f}s，扩展后交集 {v["simultaneous_sec"]:.3f}s。双方各需至少0.5秒且5%占比，交集还需至少0.3秒；本次触发={v["triggered"]}，B 中频 {p["eq"]["b_mid_cut_db"]} dB。</p>'
        log+=table(['评分项','贡献'],[[k,f'{x:+.6f}'] for k,x in p['route_score']['components'].items()])
        events=[x for x in execution['events'] if x['pair']==i+1]
        log+=table(['动作','计划串烧秒','实际串烧秒','采样序号','偏差毫秒'],[[x['name'],f'{x["planned_sec"]:.6f}',f'{x["actual_sec"]:.6f}',x['actual_sample'],f'{x["delta_ms"]:+.6f}'] for x in events])
        log+='<details><summary>本次计划原始记录</summary><pre>'+esc(json.dumps(p,ensure_ascii=False,indent=2))+'</pre></details></article>'
    log+=f'<footer>WAV 实测 {execution["levels_after"]["input_i"]} LUFS、{execution["levels_after"]["input_tp"]} dBTP；MP3 {levels["input_i"]} LUFS、{levels["input_tp"]} dBTP。实际时间来自离线应用位置；不是浏览器遥测，也不是输出鼓点复测。原报告和旧音频未覆盖。计划 ID：{plan["id"]}</footer>'
    save_page('decision-log.html','HarBeat · V2 决策日志',log)
if __name__=='__main__':main()
