import type {Plan,Track} from '../realtime/planner'
import {sectionName} from '../v31/scene'
const f=(n:number)=>n.toFixed(3)+'s'
export default function PhraseStory({a,b,p,onInspect}:{a:Track;b:Track;p:Plan;onInspect?:(id:string,t:number)=>void}){
 const ev=p.phrase!,auto=p.automation!,d=p.duration,lo=-2,hi=d+3,x=(t:number)=>150+(t-lo)/(hi-lo)*740
 const mapB=(t:number)=>t<=p.window.end?(t-p.window.start)/p.rate:d+t-p.window.end
 const line=(points:{t:number;value:number}[],y:number,scale:number)=>points.map((q,i)=>`${i?'L':'M'}${x(q.t)},${y-q.value*scale}`).join(' ')
 const bands=['low','mid','high'] as const,colors=['#51734c','#b77944','#617cb1']
 const tail=ev.exit.tailEnd-p.start,lastBeat=ev.exit.lastBeat-p.start
 const ap=a.alignment!.phrases.filter(q=>q.tailEnd>p.start+lo&&q.start<p.end+3),bp=b.alignment!.phrases.filter(q=>mapB(q.tailEnd)>lo&&mapB(q.start)<hi)
 const rect=(s:number,e:number,y:number,fill:string,key:string)=>e>lo&&s<hi?<rect key={key} x={x(Math.max(lo,s))} y={y} width={Math.max(.8,x(Math.min(hi,e))-x(Math.max(lo,s)))} height="17" rx="3" fill={fill}/>:null
 return <div className="phrase-story"><p className="story-summary">{p.reason}。A 在 <b>{f(ev.fadeStart)}</b> 才开始降低音量，在 <b>{f(p.end)}</b> 完成交接。B 从原曲 <b>{f(p.window.start)}</b> 进入，首次人声在交接时间轴 <b>{f(ev.incomingVocalRender-p.start)}</b> 出现。</p>
 <div className="story-metrics"><div><strong>{f(ev.vocalGap)}</strong><span>A 尾音至 B 首句</span></div><div><strong>{f(p.end-ev.fadeStart)}</strong><span>A 尾音后的退场时长</span></div><div><strong>{auto.kind==='adaptive'?'随能量变化':'固定模板'}</strong><span>相同选点、相同音量包络</span></div></div>
 <div className="timeline-scroll"><svg viewBox="0 0 940 345" role="img" aria-label="段落、乐句、尾音、拍点与增益对齐时间轴"><rect x={x(0)} y="30" width={x(d)-x(0)} height="280" fill="#f0f4e9"/>
 {[lo,0,d/2,d,hi].map(t=><g key={t}><line x1={x(t)} x2={x(t)} y1="25" y2="310" className="grid-line"/><text x={x(t)} y="334" textAnchor="middle">{t.toFixed(1)}s</text></g>)}
 <text x="5" y="61">A 模型乐段</text>{a.sections.map((q,i)=><g key={i}>{rect(q.start-p.start,q.end-p.start,45,'#d7e4ca','s'+i)}{q.start-p.start<hi&&q.end-p.start>lo&&<text x={x(Math.max(lo,q.start-p.start))+4} y="59" fontSize="12">{sectionName(q.label)}</text>}</g>)}
 <text x="5" y="98">A 声学乐句</text>{ap.map(q=>rect(q.start-p.start,q.end-p.start,82,'#dd9959',q.id))}
 <text x="5" y="131">A 人声保护尾音</text>{ap.map(q=>rect(q.end-p.start,q.tailEnd-p.start,115,'#c9534e',q.id))}
 <text x="5" y="164">B 声学乐句</text>{bp.filter(q=>mapB(q.tailEnd)>0).map(q=>rect(Math.max(0,mapB(q.start)),mapB(q.tailEnd),148,'#849dbb',q.id))}
 <text x="5" y="221">A 音量</text><path d={line(auto.aGain,244,40)} className="gain-a"/>
 <text x="5" y="281">B 音量</text><path d={line(auto.bGain,304,40)} className="gain-b"/>
 {[{t:0,label:'伴奏进入',y:17},{t:tail,label:'A 尾音结束',y:191},{t:lastBeat,label:'最后一拍',y:17},{t:d,label:'下一小节 / 交接',y:191}].filter(q=>q.t>=lo&&q.t<=hi).map(q=><g key={q.label}><line x1={x(q.t)} x2={x(q.t)} y1="25" y2="310" className="cue-line"/><text x={x(q.t)+(q.label==='A 尾音结束'?-8:q.label==='下一小节 / 交接'?8:0)} y={q.y} textAnchor={q.label==='A 尾音结束'?'end':q.label==='下一小节 / 交接'?'start':'middle'} fontSize="12">{q.label}</text></g>)}
 </svg></div><p className="quiet">横轴 0 = B 伴奏开始进入。最后一拍与下一小节首拍分开标示；退出点使用下一小节首拍。图示音量是总线限幅器之前的计划增益，限幅仍可能影响实际响度。声学乐句由人声证据合并得到，不代表歌词语义已确认。</p>
 <h3>本次实际 EQ 曲线 · B</h3><div className="timeline-scroll"><svg viewBox="0 0 940 190" role="img" aria-label="随时间变化的低中高频 EQ"><text x="30" y="35">0 dB</text><text x="30" y="145">−10 dB</text>{[0,-5,-10].map(db=><line key={db} x1="150" x2="890" y1={30-db*11} y2={30-db*11} className="grid-line"/>)}{bands.map((band,i)=><path key={band} d={auto.bEq.map((q,j)=>`${j?'L':'M'}${x(q.t)},${30-q[band]*11}`).join(' ')} stroke={colors[i]} strokeWidth="3" fill="none"/>)}<text x={x(0)} y="178" textAnchor="middle">进入</text><text x={x(d)} y="178" textAnchor="middle">交接 / 恢复原声</text></svg></div><div className="legend">{bands.map((band,i)=><span key={band}><i style={{background:colors[i]}}/>{['低频','中频','高频'][i]}</span>)}</div>
 <p className="quiet">{auto.kind==='adaptive'?'A 保持原始 EQ；以两曲当前频段功率、实际增益和变速映射计算 B 衰减。低 / 中 / 高频最多衰减 9 / 4 / 3 dB，只衰减、不提升。':'A 尾音前保持原始 EQ，尾音后启用原固定模板；B 使用固定模板并按计划恢复。'} 每个拐点由音频时钟执行线性平滑。预测功率不是扬声器实测。</p>
 <div className="source-cues"><div><b>A · {a.title}</b><p>声学活动结束 {f(ev.exit.voiceEnd)}<br/>保护尾音结束 {f(ev.exit.tailEnd)}<br/>最后一拍 {f(ev.exit.lastBeat)}<br/>模型段尾 {ev.exit.sectionEnd===null?'没有匹配的段尾':f(ev.exit.sectionEnd)}</p><button onClick={()=>onInspect?.(a.id,Math.max(0,ev.exit.voiceEnd-4))}>听 A 原曲句尾</button></div><div><b>B · {b.title}</b><p>进入素材 {f(p.window.start)} → {f(p.window.end)}<br/>原曲首句开始 {f(ev.incomingVocalSource)}<br/>变速率 {p.rate.toFixed(5)}<br/>接管后恢复原曲速度</p><button onClick={()=>onInspect?.(b.id,Math.max(0,ev.incomingVocalSource-3))}>听 B 原曲句首</button></div></div>
 <details><summary>原始依据：声学行号、报告指纹、每一步 EQ 的输入与结果</summary><pre>{JSON.stringify({phrase:ev,aPhrase:a.alignment!.phrases.find(q=>q.id===ev.exit.phraseId),bPhrase:b.alignment!.phrases.find(q=>q.id===ev.incomingPhraseId),automation:auto},null,2)}</pre></details>
 </div>
}
