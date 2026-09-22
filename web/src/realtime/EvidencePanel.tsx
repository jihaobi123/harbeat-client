import type {Track} from './planner'
const sec=(n:number)=>n.toFixed(1)+'s'
const value=(v:number|null|undefined)=>v==null?'缺少测量':v.toFixed(1)+' dBFS'
const reason:Record<string,string>={short_context:'片段短于8秒',not_direct_interval_inference:'只有跨段粗粒度证据',weak_model_score:'模型分数不足',ambiguous_candidates:'多个候选接近',insufficient_patches:'有效上下文不足'}
export default function EvidencePanel({track}:{track?:Track}){
 if(!track)return null
 const p=track.mixProfile
 return <section className="live-review"><h2>试听前查看：{track.title}</h2>
 {!p?<p>这首歌尚未生成段落／窗口档案。能量和局部风格请求不会用整曲标签代替。</p>:<>
 <p>保留原始段落候选，不按固定时长重切结构。能量采用统一 dBFS 功率标尺；风格为局部模型候选，尚非人工确认。</p>
 <div className="live-tablewrap"><table><thead><tr><th>原曲段落</th><th>时间范围</th><th>绝对功率</th><th>局部风格候选</th><th>证据状态</th></tr></thead><tbody>{p.sections.map(s=><tr key={s.index}><td>{s.index+1} · {s.label}</td><td>{sec(s.start)} – {sec(s.end)}</td><td>{value(s.energy?.dbfs)}</td><td>{s.style.top.slice(0,3).map(x=>`${x.style} ${x.score.toFixed(3)}`).join(' / ')||'暂无'}</td><td>{s.style.status==='model_candidate'?'模型候选 · 边界待核对':'待确认：'+s.style.reasons.map(x=>reason[x]||x).join('、')}</td></tr>)}</tbody></table></div>
 <details><summary>查看 {p.windows.length} 个候选切入窗口与接管后持续性</summary>
 <p>短前奏可以保持“待确认”；有目标风格时，另行检查接管后16秒的直接模型结果。升／降能量要求随后每4秒均保持至少1dB差值，同时限制跳变不超过6dB。</p>
 <div className="live-tablewrap"><table><thead><tr><th>窗口</th><th>进入 → 接管</th><th>进入片段风格</th><th>接管后16秒风格</th><th>连续4组功率</th></tr></thead><tbody>{p.windows.map(w=><tr key={w.id}><td>{w.id}</td><td>{sec(w.entry.start)} → {sec(w.entry.end)}</td><td>{w.entry.style.status==='needs_review'?'待确认':w.entry.style.top[0]?.style}</td><td>{w.takeover.style.status==='needs_review'?'待确认':w.takeover.style.top[0]?.style}<br/><small>{sec(w.takeover.start)} – {sec(w.takeover.end)}</small></td><td>{w.sustain.map(x=>value(x.dbfs)).join(' / ')}</td></tr>)}</tbody></table></div></details>
 <details><summary>来源与测量限制</summary><ul>{p.limitations?.map(x=><li key={x}>{x}</li>)}</ul><pre>{JSON.stringify(p.source,null,2)}</pre></details>
 </>}
 </section>
}
