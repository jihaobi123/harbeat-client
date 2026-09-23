import {useEffect,useMemo,useRef,useState} from 'react'
import {experiments,planTrial,fixedTrial,type TrialId,type RankingId,type LengthAsset} from './trials'
import {buildFixedCases,buildRankingCases,comparisonKey} from './cases'
import {LiveTransport} from '../realtime/transport'
import type {Track,Plan} from '../realtime/planner'
import DecisionHistory from '../realtime/DecisionHistory'
import logo from '../analysis/assets/harbeat-logo.png'
import '../realtime/realtime.css'
import './experiments.css'
const BASELINE='/analysis-lab-static/v3-live-baseline-20260922/index.html'
const sec=(n:number)=>Number.isFinite(n)?n.toFixed(3)+' 秒':'未知'
export function PlanCard({plan,tracks,label}:{plan:Plan|null;tracks:Track[];label:string}){
 const a=tracks.find(t=>t.id===plan?.from),b=tracks.find(t=>t.id===plan?.to)
 return <article className="trial-card"><h3>{label}</h3>{!plan?<p>这一条件下没有可执行计划。不会自动改成其他策略。</p>:<><h4>{a?.title} → {b?.title}</h4><dl><dt>A 混入 → 完全退出</dt><dd>{sec(plan.start)} → {sec(plan.end)}</dd><dt>B 原曲进入 → 正文接管</dt><dd>{sec(plan.window.start)} → {sec(plan.window.end)} · {plan.window.role}</dd><dt>转场时长 / 变速</dt><dd>{sec(plan.duration)} / ×{plan.rate.toFixed(6)}</dd><dt>两侧窗口人声占比</dt><dd>{(plan.aVocal*100).toFixed(1)}% / {(plan.bVocal*100).toFixed(1)}%</dd><dt>B 中频衰减</dt><dd>{plan.decision?.strategy.midDuck.bMidDb} dB</dd></dl><p>{plan.decision?.pointReasons.join(' ')}</p><div className="trial-sources">{[a,b].map(t=><a key={t?.id} href={`/analysis-lab?report=${encodeURIComponent(t?.reportId||'')}&tab=stems`} target="_blank" rel="noreferrer">{t?.title} · 原曲/分轨 ↗</a>)}</div><details><summary>完整选点、评分与素材来源</summary><pre>{JSON.stringify(plan,null,2)}</pre></details></>}</article>
}
export default function ExperimentLab(){
 const [caseId,setCaseId]=useState(''),[caseAssets,setCaseAssets]=useState<Record<string,LengthAsset>>({}),[feedback,setFeedback]=useState<Record<string,{trial:string;caseId:string;preference:string}>>({}),[tracks,setTracks]=useState<Track[]>([]),[catalogId,setCatalogId]=useState(''),[lengthAsset,setLengthAsset]=useState<LengthAsset>(),[audit,setAudit]=useState<any>(),[error,setError]=useState(''),[id,setId]=useState<TrialId>('vocal'),[aId,setAId]=useState(''),[target,setTarget]=useState(''),[position,setPosition]=useState(15),[busy,setBusy]=useState(false),[,refresh]=useState(0),[heard,setHeard]=useState<string[]>([]),[note,setNote]=useState(''),[rating,setRating]=useState('')
 const player=useRef<LiveTransport|null>(null),generation=useRef(0),run=useRef<string>(''),base=useRef(new URL('.',window.location.href)).current
 useEffect(()=>{let alive=true;fetch(new URL('catalog.json',base)).then(async r=>{if(!r.ok)throw new Error('实验素材目录读取失败');const raw=await r.text(),digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw));return {value:JSON.parse(raw),hash:Array.from(new Uint8Array(digest)).map(x=>x.toString(16).padStart(2,'0')).join('')}}).then(({value,hash})=>{if(alive){setTracks(value.tracks);setCatalogId(hash);setAId(value.tracks.find((t:Track)=>t.title==='Big Girls')?.id||value.tracks[0].id)}}).catch(e=>{if(alive)setError(e.message)})
 fetch(new URL('case-length-assets.json',base)).then(r=>{if(!r.ok)throw new Error('多曲对长度素材清单未就绪');return r.json()}).then(x=>{if(alive)setCaseAssets(x)}).catch(e=>{if(alive)setError(e.message)})
 fetch(new URL('length-asset.json',base)).then(r=>{if(!r.ok)throw new Error('长度素材未就绪');return r.json()}).then(x=>{if(alive)setLengthAsset(x)}).catch(e=>{if(alive)setError(e.message)})
 fetch(new URL('audit-summary.json',base)).then(r=>r.ok?r.json():null).then(x=>{if(alive)setAudit(x)}).catch(()=>{})
 return()=>{alive=false;generation.current++;player.current?.dispose()}
 },[base])
 const fixed=['eq','material','length'].includes(id),cfg=experiments[id],p=player.current
 const fixedCases=useMemo(()=>buildFixedCases(tracks),[tracks]),rankingCases=useMemo(()=>buildRankingCases(tracks),[tracks])
 const choices=fixed?fixedCases.map(c=>({...c,label:`${tracks.find(t=>t.id===c.aId)?.title} → ${tracks.find(t=>t.id===c.bId)?.title} · ${c.position} 秒`})):rankingCases
 const selected=choices.find(c=>c.id===caseId)||((caseId==='custom'&&!fixed)||(caseId==='legacy'&&fixed)?null:choices[0]),selectedId=selected?.id||(fixed?'legacy':'custom')
 const fixedSpec=fixedCases.find(c=>c.id===selectedId)
 const comparison=useMemo(()=>{try{if(!tracks.length)return null;if(fixed){const f=fixedTrial(tracks,id as 'eq'|'material'|'length',fixedSpec?caseAssets[fixedSpec.id]:lengthAsset,fixedSpec);return {a:f.a,position:f.position,baseline:f.baseline,variant:f.variant,searches:null}}
 const sourcePosition=selected?.position??position,sourceId=selected?.aId??aId
 const a=tracks.find(t=>t.id===sourceId);if(!a||!Number.isFinite(sourcePosition)||sourcePosition<0||sourcePosition>=a.duration)throw new Error('请选择有效的歌曲和原曲触发位置');const b=planTrial(a,tracks,sourcePosition,'baseline',selected?undefined:target||undefined),v=planTrial(a,tracks,sourcePosition,id as RankingId,selected?undefined:target||undefined);return {a,position:sourcePosition,baseline:b.best,variant:v.best,searches:{baseline:b,variant:v}}
 }catch(e){return {error:(e as Error).message}}},[tracks,id,aId,target,position,lengthAsset,fixed,fixedSpec,selected?.id,caseAssets])
 const fingerprint=comparison&&!('error' in comparison)?JSON.stringify([comparison.position,...[comparison.baseline,comparison.variant].map(p=>p&&[p.id,p.asset.sha256,p.start,p.end,p.decision?.strategy.midDuck.bMidDb])]):'not-ready'
 const key=comparisonKey(catalogId,id,selectedId,fingerprint),currentHeard=heard.filter(x=>x.startsWith(key+':'))
 useEffect(()=>{setNote('');setRating('')},[key])
 const bothCompleted=currentHeard.includes(key+':baseline')&&currentHeard.includes(key+':variant')
 useEffect(()=>{if(p?.logs.some(x=>x.kind==='comparison_finished'&&x.comparisonId===run.current)){const stamp=run.current;setHeard(prev=>prev.includes(stamp)?prev:[...prev,stamp])}},[p?.logs.length])
 function stop(){generation.current++;player.current?.stop();setBusy(false)}
 async function play(arm:'baseline'|'variant'){
  if(!comparison||'error' in comparison)return;const plan=comparison[arm];if(!plan)return
  const token=++generation.current;setError('');setBusy(true);setRating('')
  try{if(!player.current){const live=new LiveTransport(tracks,()=>refresh(x=>x+1),base);player.current=live;await live.initialize();if(token!==generation.current)return}
   const live=player.current!;run.current=key+':'+arm
   live.log('comparison_analysis',{comparisonId:run.current,catalogSha256:catalogId,experimentId:id,caseId:selectedId,arm,config:cfg,referenceCommit:'279b65d',comparison})
   await live.playComparison(plan,comparison.position,{experimentId:id,caseId:selectedId,arm,comparisonId:run.current,midDb:id==='eq'&&arm==='variant'?-8:-5,horizonSec:arm==='baseline'?18:cfg.horizonSec,config:arm==='baseline'?experiments.baseline:cfg,catalogSha256:catalogId})
  }catch(e){if(token===generation.current)setError((e as Error).message)}finally{if(token===generation.current)setBusy(false)}
 }
 function download(){if(!p)return;const blob=new Blob([JSON.stringify(p.export(),null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`HarBeat-${id}-comparison.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 function rate(value:string){if(!p||!bothCompleted)return;p.log('listening_comparison',{experimentId:id,caseId:selectedId,comparisonKey:key,preference:value,note,config:cfg,catalogSha256:catalogId});setFeedback(prev=>({...prev,[key]:{trial:id,caseId:selectedId,preference:value}}));setRating('已记录：'+value)}
 const locked=busy||Boolean(p?.active),same=comparison&&!('error' in comparison)&&comparison.baseline&&comparison.variant&&comparison.baseline.id===comparison.variant.id
 return <main className="live-shell trial-shell"><header className="live-header"><a className="live-brand" href="/analysis-lab"><img src={logo}/><span>HarBeat<small>CONTROLLED LIVE TRIALS</small></span></a><a href={BASELINE}>返回冻结 V3 实时版 ↗</a></header>
 <section className="live-intro"><div><span className="live-eyebrow">一次只改一件事</span><h1>先把接歌做好。</h1><p>每项独立对比已认可的 V3 实时基线。歌曲在浏览器实时叠加、EQ 和淡化；能量与目标风格筛选关闭。</p></div><aside><b>保留你的基线</b><p>每项都从同一个基线出发，不累计前项改动。</p><small>客观统计只说明规则发生了什么，是否好听由你试听判断。</small></aside></section>
 <nav className="trial-tabs" aria-label="独立实验">{(Object.keys(experiments) as TrialId[]).filter(x=>x!=='baseline').map(x=><button disabled={locked} aria-pressed={id===x} onClick={()=>{setId(x);setRating('');setNote('')}} key={x}>{experiments[x].title}</button>)}</nav>
 <section className="live-review"><h2>{cfg.title}</h2><p className="trial-change">{cfg.change}</p><p>固定：原始分析、人声检测方法、主增益与淡化曲线。固定素材实验中的人声触发开关也沿用参照，避免额外改变 EQ。</p>
 <section className="trial-case-picker"><h3>多曲对试听 · {choices.length} 个预设场景</h3><p>轮换覆盖现有 6 首歌曲，同一场景内比较参照与实验。人声占比普遍较高；此曲库还不能代表无人声、慢歌和其他曲风。</p><label>试听场景<select aria-label="试听场景" disabled={locked} value={selectedId} onChange={e=>setCaseId(e.target.value)}>{choices.map((c,i)=><option key={c.id} value={c.id}>{i+1}. {c.label}{Object.values(feedback).some(f=>f.trial===id&&f.caseId===c.id)?' · 已评价':''}</option>)}<option value={fixed?'legacy':'custom'}>{fixed?'原始例子：Big Girls → Cold · 15 秒':'自定义歌曲 / 触发点'}</option></select></label><div className="trial-play"><button disabled={locked||!selected||choices.indexOf(selected)===0} onClick={()=>setCaseId(choices[choices.indexOf(selected!)-1].id)}>上一组</button><button disabled={locked||!selected||choices.indexOf(selected)>=choices.length-1} onClick={()=>setCaseId(choices[choices.indexOf(selected!)+1].id)}>下一组</button><span>本项已评价 {choices.filter(c=>Object.values(feedback).some(f=>f.trial===id&&f.caseId===c.id)).length} / {choices.length} 组</span></div><p className="live-muted">预设按曲目覆盖与可执行条件选择，不按“实验是否获胜”挑例子。前三项保留选点相同、没有可执行参照的情况。后三项使用 12 个不同曲对；Crazy Love 的 4 小节退出窗口未通过当前拍网格限制，仅作为进入曲目参与。</p></section>
 {fixed?<p>本组固定选点；两侧卡片显示具体曲对与原曲时刻。更换组别会切换曲对，组内只改变本项变量。</p>:<div className="trial-controls"><label>当前歌曲<select disabled={locked} value={selected?.aId??aId} onChange={e=>{setAId(e.target.value);setPosition(selected?.position??position);setCaseId('custom');setTarget('')}}>{tracks.map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label><label>原曲触发位置（秒）<input type="number" min="0" step="1" disabled={locked} value={selected?.position??position} onChange={e=>{setAId(selected?.aId??aId);setPosition(e.target.valueAsNumber);setCaseId('custom')}}/></label><label>下一首范围<select disabled={locked} value={selected?'':target} onChange={e=>{setAId(selected?.aId??aId);setPosition(selected?.position??position);setCaseId('custom');setTarget(e.target.value)}}><option value="">在全部候选中选择</option>{tracks.filter(t=>t.id!==(selected?.aId??aId)).map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label></div>}
 {audit&&!fixed&&<details><summary>六首真实素材的规则对照结果（非听感评分）</summary><pre>{JSON.stringify(audit.summary?.find((x:any)=>x.trial===id),null,2)}</pre><div className="trial-cases">{audit.changedCases?.filter((c:any)=>c.trial===id).slice(0,10).map((c:any,i:number)=><button key={i} disabled={locked} onClick={()=>{setCaseId('custom');setAId(tracks.find(t=>t.title===c.a)!.id);setPosition(c.position);setTarget('')}}>{c.a} · {c.position} 秒</button>)}</div></details>}
 {error&&<p role="alert" className="live-error">{error}</p>}{comparison&&'error' in comparison&&<p role="alert">{comparison.error}</p>}
 {comparison&&!('error' in comparison)&&<><div className="trial-grid"><PlanCard label="参照版本" plan={comparison.baseline} tracks={tracks}/><PlanCard label="本项实验" plan={comparison.variant} tracks={tracks}/></div>{same&&<p className="trial-neutral">本场景的选歌和选点相同。修改参数不保证改变结果，可查看其他触发位置。</p>}
 <div className="trial-play"><button className="live-primary" disabled={locked||!comparison.baseline} onClick={()=>void play('baseline')}>实时播放参照</button><button className="live-primary" disabled={locked||!comparison.variant} onClick={()=>void play('variant')}>实时播放本项实验</button><button onClick={stop}>停止</button><button disabled={!p?.logs.length} onClick={download}>导出本次对照日志</button></div>
 <p role="status">{p?.status||'先查看计划，再分别试听参照与实验。'} {p?.active&&`· 当前原曲 ${sec(p.position)}`}</p><p className="live-muted">先下载并校验本次素材，再从触发点前 4 秒开始；交接后继续播放 8 秒。音量固定为两版相同。所有声音混合实时执行，进入变速片段提前准备。</p>
 <h3>你的试听结论</h3><textarea value={note} onChange={e=>setNote(e.target.value)} placeholder="例如：人声更清楚，但等待稍长；或副歌被提前切断"/><div className="trial-play">{['参照更好','实验更好','差不多','都有问题'].map(v=><button disabled={!bothCompleted} key={v} onClick={()=>rate(v)}>{v}</button>)}</div><p>{rating||feedback[key]?.preference||'两段都播放到结束后，可以记录偏好；统计不会代替你的选择。'}</p></>}
 </section><DecisionHistory logs={p?.logs||[]} eventCount={p?.logs.length||0} tracks={tracks}/><footer><p>原始结构和人声区间尚未逐首人工确认。日志中的实际时间是音频线程观察，不是扬声器／蓝牙测量。会话保存在本浏览器，可导出共享。</p><a href="audit-summary.json">下载规则对照摘要</a> · <a href={BASELINE}>冻结基线</a></footer></main>
}
