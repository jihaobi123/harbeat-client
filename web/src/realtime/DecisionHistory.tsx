import {memo,useMemo,useState} from 'react'
import type {Track} from './planner'
import type {Log} from './transport'
const label:Record<string,string>={next:'下一首',up:'提高能量',down:'降低能量',style:'切换风格',completed:'交接完成',cancelled:'已取消',superseded:'被新请求替代',stopped:'播放停止',failed:'未执行',expired:'等待超时',rejected:'请求未受理'}
const phase:Record<string,string>={ready_assets:'检查已就绪素材',preparation_preview:'选择待准备素材',after_preparation:'素材准备后重新选点'}
const num=(x:number)=>Number.isFinite(x)?x.toFixed(3):'未知'
const title=(tracks:Track[],id:string)=>tracks.find(t=>t.id===id)?.title||id||'无播放曲目'
function entries(logs:Log[]){return logs.filter(e=>e.kind==='request_received').map(trigger=>{
 const events=logs.filter(e=>e.requestId===trigger.requestId)
 return {trigger,events,scheduled:events.find(e=>e.kind==='plan_scheduled'),outcome:events.find(e=>e.kind==='request_outcome'),searches:events.filter(e=>e.kind==='decision_search')}
})}
export function decisionReport(logs:Log[],tracks:Track[]){
 const rows=['# HarBeat V3 在线混音决策日志','','时间均标明原曲或 AudioContext；音频线程记录不等于扬声器出声实测。','固定 V3 模板，未比较其他混音算法；当前页面会话完整导出。','']
 for(const {trigger:r,events,scheduled:s,outcome:o,searches} of entries(logs)){
  rows.push(`## ${r.requestId}`,`${r.wallTime} · ${r.origin==='source_end_auto'?'曲目将结束自动触发':'用户触发'} · ${label[r.intent.kind]||r.intent.kind}`,`当前曲目：${title(tracks,r.sourceTrackId)}；原曲 ${num(r.sourcePosition)} 秒；预算 ${r.budgetSec} 秒。`,`目标：${r.intent.targetId?title(tracks,r.intent.targetId):r.intent.style||'不限风格'}；能量 ${r.intent.energy||r.intent.kind}。`,`结果：${o?`${label[o.outcome]||o.outcome} — ${o.reason}`:s?'已安排，尚无最终结果':'处理中／等待中'}`,'')
  if(s){const d=s.plan.decision
   rows.push(`选择：${title(tracks,s.plan.from)} → ${title(tracks,s.plan.to)}`,`为什么胜出：${s.selection.reason}；合格候选 ${s.selection.candidateCount} 个。`,...d.pointReasons.map((x:string)=>`- ${x}`),`混音方案：${d.strategy.selectionReason}`,`人声处理：${d.strategy.midDuck.reason}`,`低频处理：${d.strategy.eq.lowReason}`,`恢复：${d.strategy.restore.reason}`,`规则分：${d.score.total}；${d.score.components.map((x:any)=>`${x.label} ${x.contribution}`).join('；')}`,`计划 AudioContext：B 开始 ${num(s.start)} 秒，EQ 恢复 ${num(s.restore)} 秒，交接完成 ${num(s.end)} 秒。`,'', '预处理、映射与自动化依据：','```json',JSON.stringify(d,null,2),'```','')
  }
  for(const search of searches){rows.push(`### ${phase[search.phase]||search.phase}`,`剩余预算 ${num(search.remainingBudgetSec)} 秒；合格候选 ${search.result.candidateCount} 个。`)
   for(const e of search.result.exclusions)rows.push(`- ${e.track}${e.windowId?' / '+e.windowId:''}：${e.reason}（${e.code}，${e.count} 次筛除）`)
   rows.push('候选排序：','```json',JSON.stringify(search.result.candidates,null,2),'```','')
  }
  for(const e of events.filter(e=>e.kind==='audio_observation'))rows.push(`音频线程：${e.name}；计划 ${num(e.plannedContextSec)} 秒，观察 ${num(e.observedContextSec)} 秒，偏差 ${num(e.observationDeltaMs)} ms。`)
  rows.push('事件链：','```json',JSON.stringify(events.map(({kind,contextSec,reason,planId,outcome,phase})=>({kind,contextSec,reason,planId,outcome,phase})),null,2),'```','')
 }
 return rows.join('\n')
}
export default memo(function DecisionHistory({logs,tracks,eventCount=logs.length}:{logs:Log[];tracks:Track[];eventCount?:number}){
 const [limit,setLimit]=useState(20);const all=useMemo(()=>entries(logs),[eventCount,logs])
 function download(){const url=URL.createObjectURL(new Blob([decisionReport(logs,tracks)],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='HarBeat-V3-Live-decisions.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 return <section className="live-review live-decision-history"><div className="live-sectiontop"><div><h2>逐次混音决策日志</h2><p>每次触发保留独立编号、选择依据和最终结果。</p></div><button disabled={!all.length} onClick={download}>导出决策说明 ↓</button></div>
 <p className="live-muted">本页保留当前会话全部日志，不再删除较早记录。关闭或刷新前请导出；尚未自动保存到服务器。</p>
 {!all.length&&<p>点击下一首、能量或风格后，这里会逐次显示；没有找到方案也会记录。</p>}
 {all.slice(-limit).reverse().map(({trigger:r,events,scheduled:s,outcome:o,searches})=><details className="live-decision" key={r.requestId}>
  <summary>{label[r.intent.kind]||r.intent.kind}{r.intent.style?' · '+r.intent.style:''}{r.intent.energy&&r.intent.energy!=='any'?' · '+(r.intent.energy==='up'?'持续提高能量':'持续降低能量'):''} · {o?label[o.outcome]:s?'已安排':events.some(e=>e.kind==='request_deferred')?'等待当前交接':'准备中'} · {r.wallTime}</summary>
  <p><code>{r.requestId}</code></p><p>{r.origin==='source_end_auto'?'曲目将结束，自动触发':'用户触发'}；{title(tracks,r.sourceTrackId)} 原曲 {num(r.sourcePosition)} 秒；等待预算 {r.budgetSec} 秒{r.intent.targetId?`；指定 ${title(tracks,r.intent.targetId)}`:''}。</p>
  {o&&<p><b>{label[o.outcome]||o.outcome}：</b>{o.reason}</p>}
  {s&&<><h3>{title(tracks,s.plan.from)} → {title(tracks,s.plan.to)}</h3><p>{s.selection.reason}。合格候选 {s.selection.candidateCount} 个；规则分 {num(s.plan.score)}{s.selection.runnerUp?`，与第二名相差 ${num(s.selection.runnerUp.gap)}`:''}。</p>
   <ul>{s.plan.decision.pointReasons.map((x:string,i:number)=><li key={i}>{x}</li>)}</ul>
   <h4>为什么采用这个混音方案</h4><p>{s.plan.decision.strategy.selectionReason}</p><p>{s.plan.decision.strategy.midDuck.reason}</p><p>{s.plan.decision.strategy.eq.lowReason} {s.plan.decision.strategy.restore.reason}</p>
   <div className="live-tablewrap"><table><thead><tr><th>评分依据</th><th>原始值</th><th>权重</th><th>贡献</th></tr></thead><tbody>{s.plan.decision.score.components.map((c:any)=><tr key={c.key}><td>{c.label}</td><td>{num(c.value)}</td><td>{c.weight}</td><td>{num(c.contribution)}</td></tr>)}</tbody></table></div>
   <details><summary>查看预处理来源、人声区间、变速与 EQ 参数</summary><pre>{JSON.stringify(s.plan.decision,null,2)}</pre></details>
  </>}
  {searches.map((search,i)=><details key={i}><summary>{phase[search.phase]||search.phase}：{search.result.candidateCount} 个合格候选</summary>
   <p>剩余预算 {num(search.remainingBudgetSec)} 秒；下列次数是逐项筛除次数，并非互相独立的歌曲数量。</p><ul>{search.result.exclusions.map((x:any,j:number)=><li key={j}>{x.track}{x.windowId?' / '+x.windowId:''}：{x.reason}（{x.count} 次）</li>)}</ul>
   <div className="live-tablewrap"><table><thead><tr><th>排名</th><th>歌曲</th><th>A 混入／退出（原曲秒）</th><th>得分</th></tr></thead><tbody>{search.result.candidates.slice(0,10).map((c:any)=><tr key={c.id}><td>{c.rank}</td><td>{title(tracks,c.to)}</td><td>{num(c.start)} / {num(c.end)}</td><td>{num(c.score)}</td></tr>)}</tbody></table></div><small>页面显示前 10 名；完整候选和逐项贡献在导出文件中。</small>
  </details>)}
  <details><summary>本次请求事件链（{events.length} 条）</summary><pre>{JSON.stringify(events,null,2)}</pre></details>
 </details>)}
 {all.length>limit&&<button onClick={()=>setLimit(limit+20)}>查看更早的 20 次触发</button>}
 </section>
})
