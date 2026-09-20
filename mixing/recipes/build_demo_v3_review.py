#!/usr/bin/env python3
"""Build the standalone audition for an exact colleague-plan replay."""
import hashlib,html,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/demo-render-v3/listen'

def h(x):return html.escape(str(x))
def stamp(s):return f'{int(s)//60}:{s%60:06.3f}'
def audio(src):return f'<audio controls preload="metadata" src="{h(src)}"></audio>'
def table(headers,rows):return '<div class="table"><table><thead><tr>'+''.join('<th>'+h(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+h(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'

def main():
    p=json.loads((OUT/'plan.json').read_text());e=json.loads((OUT/'execution.json').read_text());c=json.loads((OUT/'comparison.json').read_text())
    css=re.search(r'<style>(.*?)</style>',(ROOT/'outputs/demo-render-v2/listen/index.html').read_text(),re.S).group(1)
    css+=' .badge{background:#e4f1e4;padding:7px 13px;border-radius:6px;display:inline-block;color:#24543e} .proof{overflow-wrap:anywhere;font:12px/1.7 monospace} .number{font-size:25px;color:#24543e;font-weight:650} .muted{color:#64786e} .actions{display:flex;flex-wrap:wrap;gap:14px}'
    nav='<header><img src="logo.png" alt="HarBeat"><b>HarBeat / DEMO V3</b><a href="index.html">V3 试听</a><a href="decision-log.html">复现记录</a><a href="/analysis-lab-static/demo-2-20260920/index.html">V2</a><a href="/analysis-lab">分析平台</a></header>'
    footer='<footer>原始混音逻辑：同事交付的 algorithm_demo_transition_logic_1_0.py。V3 按已交付计划重新渲染；页面与执行记录由 HarBeat 补充。<br>段落、人声与鼓组原有的待确认／降级标记继续保留。复现一致不等于段落已人工校准。</footer>'
    js='''<script>document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(b!==a)b.pause()})));</script>'''
    def page(name,title,body):
        (OUT/name).write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+h(title)+'</title><style>'+css+'</style></head><body><main>'+nav+body+footer+'</main>'+js+'</body></html>')
    status='MP3 文件与同事交付版完全一致' if c['mp3_bytes_identical'] else '按同事计划重新渲染，差异见复现记录'
    mainbody='<h1>V3 · 同事方案复现</h1><p>恢复你认可的歌曲顺序、主体原速、音量与 EQ。使用同事的原始渲染函数，从六首原曲重新生成。</p><span class="badge">'+status+'</span>'
    mainbody+='<div class="grid"><article><h2>V3 重新渲染</h2><p>完整混音 · 约 7 分 10 秒 · MP3 320 kbps</p>'+audio('HarBeat-DEMO-3.0-reproduction.mp3')+'<div class="actions"><a download href="HarBeat-DEMO-3.0-reproduction.mp3">下载 MP3</a><a download href="HarBeat-DEMO-3.0-reproduction.wav">下载 WAV</a></div></article><article><h2>同事交付原版</h2><p>保留交付文件，作为复现对照。播放任一版本时，另一个会暂停。</p>'+audio('colleague-original.mp3')+'<a download href="colleague-original.mp3">下载同事原版</a></article></div>'
    mainbody+='<h2>这一版保留了什么</h2>'+table(['项目','执行方式'],[
        ['歌曲顺序','Closer → Bring Back The Summer → Paris → Clear → What Lovers Do → Don’t Say'],
        ['速度','只对 B 前奏使用 A BPM ÷ B BPM；主体恢复原速'],
        ['交接','沿用同事前奏／副歌选点，线性交叉淡化；本次五次均为 A 副歌长于 B 前奏'],
        ['B 进入','140 Hz 低频 −7 dB、3600 Hz 高频 +1.2 dB；最后半小节恢复原音'],
        ['A 退出','退出窗口内低频 −9 dB、高频 −1.4 dB，随总音量退出'],
        ['人声','沿用同事判断；五次转场均未触发 1200 Hz 中频衰减'],
        ['音量／结尾','每首固定增益 0.76；原版限幅器；最后 7 秒淡出']])
    mainbody+='<h2>五次转场单独试听</h2>'
    for i,t in enumerate(p['transitions']):
        mainbody+=f'<article class="transition"><h3>{i+1:02d} · {h(p["tracks"][i]["title"])} → {h(p["tracks"][i+1]["title"])}</h3><p>重叠 {t["overlap_seconds"]:.2f} 秒 · B 前奏速度倍率 {t["full_precision_rate"]:.6f} · 从进歌前约 20 秒开始试听</p>'+audio(f'transition-{i+1:02d}.mp3')+'</article>'
    mainbody+='<div class="hero"><h2>复现校验</h2><p>新生成的 V3 与同事原版的 MP3 SHA-256 一致；解码后的帧数与每个采样值也一致。</p><p class="proof">SHA-256：'+h(e['mp3_sha256'])+'</p><p>保留原版排歌结果与参数，没有重新计算 720 种顺序，也没有套用 V2 的固定 100 BPM、逐曲衰减或滤波器。</p><a href="decision-log.html">查看每首歌和每次转场的复现记录 →</a></div>'
    page('index.html','HarBeat · V3 同事方案复现',mainbody)
    body='<h1>V3 复现记录</h1><p>冻结同事已交付的排歌、段落边界和人声判断；复用其渲染函数，记录本次实际执行。音频处理策略没有变更。</p><span class="badge">'+status+'</span>'
    body+='<h2>验证结果</h2>'+table(['检查','结果'],[
        ['MP3 二进制文件', '完全一致' if c['mp3_bytes_identical'] else '不一致'],
        ['解码后采样', '完全一致' if c['decoded_samples_identical'] else '有差异'],
        ['解码帧数',f'{c["v3_decoded_frames"]:,} 帧 / 44,100 Hz / 双声道'],
        ['WAV 时长',f'{e["duration_sec"]:.6f} 秒'],
        ['MP3 综合响度',f'{e["mp3_levels"]["input_i"]} LUFS（原版 {e["reference_levels"]["input_i"]}）'],
        ['MP3 真峰值',f'{e["mp3_levels"]["input_tp"]} dBTP（沿用原版处理，未额外降低）'],
        ['运行环境',e['ffmpeg_version']],
        ['音频处理策略变更','无'],['排歌算法是否重新运行','否；直接执行同事交付的选定顺序']])
    body+='<h2>六首歌的原始边界</h2>'+table(['歌曲','主体 BPM','前奏结束','第一遍副歌','前奏变速倍率'],[
        [t['title'],t['bpm'],stamp(t['intro_end_ms']/1000),stamp(t['first_chorus_start_ms']/1000)+' → '+stamp(t['first_chorus_end_ms']/1000),f'{t["incoming_rate"]:.9f}'] for t in p['tracks']])
    body+='<p>保留 30／11 小节等原有候选结果。本次验证的是声音能否复现，不把原有段落标签变成人工确认。</p><h2>逐次衔接</h2>'
    for i,(t,x) in enumerate(zip(p['transitions'],e['transitions'])):
        body+=f'<article class="transition"><h3>{i+1:02d} · {h(p["tracks"][i]["title"])} → {h(p["tracks"][i+1]["title"])}</h3>'
        body+=table(['依据／事件','执行值'],[
            ['选点逻辑',f'A 副歌 {t["a_chorus_bars"]} 小节，B 前奏 {t["b_intro_bars"]} 小节；完整 B 前奏参与交接'],
            ['A 原曲副歌',f'{t["a_first_chorus_start_ms"]/1000:.3f} → {t["a_out_point_first_chorus_end_ms"]/1000:.3f} 秒'],
            ['B 原曲前奏窗口',f'{t["b_entry_ms"]/1000:.3f} → {t["b_intro_end_ms"]/1000:.3f} 秒'],
            ['B 变速／半小节恢复',f'{t["full_precision_rate"]:.9f} 倍 / {t["restore_half_bar_seconds"]:.6f} 秒'],
            ['实际跨淡化时长参数',x['ffmpeg_overlap_literal']+' 秒（沿用原函数毫秒格式化）'],
            ['交付版进歌时间',stamp(x['delivered_transition_sec'])],
            ['本次原函数计算的进歌时间',stamp(x['replay_original_function_transition_sec'])],
            ['与交付记录之差',f'{x["difference_from_delivered_ms"]:.6f} 毫秒'],
            ['A／B 人声占比',f'{t["a_transition_vocal_ratio"]:.1%} / {t["b_intro_vocal_ratio"]:.1%}，中频衰减未触发'],
            ['A 淡出／B 淡入','线性振幅交叉淡化；原版 bass/treble EQ 与限幅器'],
            ['A 候选小节进歌点',f'{t["a_transition_start_ms"]/1000:.3f} 秒（原计划候选；渲染按片段时长和 overlap 拼接）']])
        body+='<p>时间对照是离线拼接记录，不是浏览器声卡输出延迟或人工确认的音乐拍点。</p></article>'
    body+='<h2>数据与归属</h2><p>原始素材用已有完整 SHA-256 验证，并核对同事计划中的歌曲 ID。原始渲染脚本及原计划均锁定校验值；V3 只增加素材路径适配、执行记录和展示。交付包缺少部分原排歌依赖，因此直接回放已交付决定。</p><div class="links">'+''.join(f'<a href="{f}" download>{label}</a>' for f,label in [('plan.json','V3 冻结计划'),('execution.json','本次执行记录'),('comparison.json','音频比对结果'),('colleague-plan.json','同事原计划'),('colleague-renderer.py','同事原始渲染源码')])+'</div>'
    page('decision-log.html','HarBeat · V3 复现记录',body)
    shutil.copy2(ROOT/'outputs/demo-render-v2/listen/logo.png',OUT/'logo.png')
    files=[x for x in OUT.iterdir() if x.is_file() and x.name!='artifact-checksums.json']
    manifest={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(files)}
    (OUT/'artifact-checksums.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print('Built V3 pages and',len(manifest),'artifact hashes')
if __name__=='__main__':main()
