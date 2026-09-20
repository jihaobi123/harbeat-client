import { useEffect,useState,type ReactNode } from 'react'
import { call,post } from './api'
import { Report,download,series,timeLabel } from './data'
import { Curve,Segments } from './Charts'

const labels:Record<string,string>={intro_start:'前奏开始',intro_end:'前奏结束',verse_start:'第一遍主歌开始',chorus_start:'第一遍副歌开始',chorus_end:'第一遍副歌结束'}
const states:Record<string,string>={ready:'已确认，可生成计划',needs_review:'需要试听确认',blocked:'信息不足，暂不可执行'}
const fmt=(v:any,digits=3)=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(digits):'—'
const stamp=(v:any)=>typeof v==='number'&&Number.isFinite(v)?timeLabel(v):'—'

export function CalibrationGuard({matches,children}:{matches:boolean;children:ReactNode}){
 return <>{!matches&&<p className="lab-alert">当前试听的是未核验的本地文件。请先点击“返回报告原曲”，再校准和确认本曲。</p>}<fieldset disabled={!matches} style={{border:0,padding:0,margin:0,minWidth:0}}>{children}</fieldset></>
}

export function regularGrid(bpm:number,first:number,duration:number){
 if(!Number.isFinite(bpm)||bpm<40||bpm>240||!Number.isFinite(first)||first<0||first>=duration||duration>7200)throw new Error('请填写 40–240 BPM、时长内的第一小节首拍')
 const step=60/bpm,beats:number[]=[],downbeats:number[]=[]
 for(let i=0;first+i*step<=duration+.000001;i++){const t=Number((first+i*step).toFixed(6));beats.push(t);if(i%4===0)downbeats.push(t)}
 return {beats,downbeats,numerator:4,denominator:4}
}

export function DJReadiness({data}:{data:any}){
 return <><p className="lab-notice">校准状态：{({current:'当前有效',stale:'已过期，分析输入发生变化，请重新核对',not_reviewed:'尚未确认'} as any)[data.review.status]} · 人声区间：{data.vocals.intervals===null?'未知':`${data.vocals.intervals.length} 段候选`}</p>
 <div className="lab-module-grid">{[['incoming','作为 B 进歌'],['outgoing','作为 A 出歌']].map(([role,title])=>{const r=data.roles[role];return <section key={role} className="lab-module"><h3>{title}</h3><b>{states[r.status]}</b><p>{r.bar_count??'—'} 个小节</p>{r.issues.map((x:any,i:number)=><p key={x.code+i} className={x.severity==='needs_review'?'lab-muted':'lab-alert'}>{x.message}</p>)}</section>})}</div></>
}

export function PlanPreview({plan}:{plan:any}){
 return <section className="lab-panel"><h3>试听前的接歌计划</h3><p><b>{states[plan.status]}</b>{plan.a_title&&` · ${plan.a_title} → ${plan.b_title}`}</p>
 {plan.issues.map((x:any,i:number)=><p className="lab-alert" key={x.code+i}>{x.track?`${x.track}：`:''}{x.message}</p>)}
 {plan.mapping&&<><p>{({equal:'副歌与前奏等长',a_longer:'A 副歌较长',b_longer:'B 前奏较长'} as any)[plan.case]} · 衔接 {plan.overlap_bars} 小节 · 目标 {fmt(plan.target_bpm,2)} BPM</p>
 <div className="lab-table-wrap"><table><thead><tr><th>项目</th><th>A 当前歌曲</th><th>B 下一首</th></tr></thead><tbody>
 <tr><td>局部原速 / 播放倍率</td><td>{fmt(plan.mapping.a.source_bpm_local,2)} / {fmt(plan.mapping.a.rate,4)}</td><td>{fmt(plan.mapping.b.source_bpm_local,2)} / {fmt(plan.mapping.b.rate,4)}</td></tr>
 <tr><td>原文件起播位置</td><td>{stamp(plan.mapping.a.source_cue_sec)}</td><td>{stamp(plan.mapping.b.source_cue_sec)}</td></tr>
 <tr><td>局部响度</td><td>{fmt(plan.gains.a_lufs,2)} LUFS</td><td>{fmt(plan.gains.b_lufs,2)} LUFS</td></tr>
 <tr><td>响度与叠加余量衰减</td><td>{fmt(plan.gains.a_trim_db,2)} dB</td><td>{fmt(plan.gains.b_trim_db,2)} dB</td></tr>
 </tbody></table></div><p>变速映射后的最大拍点偏差：{fmt(plan.mapping.max_beat_error_ms,1)} ms。比较的是已有拍网格，不代表实际播放误差。</p>
 <p>B 中频预设：{fmt(plan.eq.b_mid_cut_db,1)} dB · {plan.eq.low_hz}–{plan.eq.high_hz} Hz · 最后半小节恢复至 0 dB。整曲增益完成 A → B 交接。</p>
 <p>人声规则：{plan.vocal_overlap.rule_triggered===null?'区间未知':plan.vocal_overlap.rule_triggered?'两段均含人声，触发 B 中频衰减':'未触发'} · 映射后实际重叠候选 {plan.vocal_overlap.simultaneous_intervals.length} 段。</p></>}
 <div className="lab-table-wrap"><table><thead><tr><th>事件</th><th>计划发生时间</th><th>实际发生时间</th><th>偏差</th></tr></thead><tbody>{plan.events.map((e:any)=><tr key={e.event_id}><td>{e.name}</td><td>{stamp(e.planned_sec)}</td><td>{e.actual_sec==null?'未执行':stamp(e.actual_sec)}</td><td>{e.actual_sec==null?'—':`${fmt((e.actual_sec-e.planned_sec)*1000,1)} ms`}</td></tr>)}</tbody></table></div>
 <p className="lab-muted">播放器执行日志尚未接入；此表展示可导出的计划，普通原曲试听不会生成“实际发生时间”。EQ 与响度参数需要在正式转场渲染后复测。</p>
 <button onClick={()=>download('dj-transition-plan.json',JSON.stringify(plan,null,2))}>导出这份计划</button></section>
}

export default function DJPanel({report,history,cursor,onSeek,busy,onRun,auditionMatches=true}:{report:Report;history:any[];cursor:number;onSeek:(t:number)=>void;busy:boolean;onRun:()=>Promise<void>;auditionMatches?:boolean}){
 const [data,setData]=useState<any>(null),[error,setError]=useState(''),[saving,setSaving]=useState(false)
 const [anchors,setAnchors]=useState<Record<string,string>>({}),[checks,setChecks]=useState<Record<string,boolean>>({})
 const [gridEdit,setGridEdit]=useState<any>(null),[bpm,setBpm]=useState(''),[first,setFirst]=useState('')
 const [vocalEdit,setVocalEdit]=useState(false),[vocalText,setVocalText]=useState('[]'),[note,setNote]=useState('')
 const [next,setNext]=useState(''),[policy,setPolicy]=useState(''),[target,setTarget]=useState(''),[plan,setPlan]=useState<any>(null)
 const [savedForm,setSavedForm]=useState('')
 const dirty=savedForm!==JSON.stringify({anchors,checks,gridEdit,vocalEdit,vocalText,note})
 function update(d:any){
  setData(d);const current=d.review.status==='current'?d.review.current:null
  setAnchors(Object.fromEntries(Object.entries(d.anchors).map(([k,v]:[string,any])=>[k,String(v.edited_sec??v.raw_sec??'')])))
  setChecks(current?.confirmations||{});setGridEdit(current?.grid||null)
  setBpm(d.grid.bpm?String(Number(d.grid.bpm.toFixed(3))):'');setFirst(String(d.grid.downbeats[0]??0))
  setVocalEdit(Boolean(current?.vocal_intervals));setVocalText(JSON.stringify(current?.vocal_intervals??d.vocals.intervals??[],null,2));setNote(current?.note||'');setPlan(null)
  setSavedForm(JSON.stringify({anchors:Object.fromEntries(Object.entries(d.anchors).map(([k,v]:[string,any])=>[k,String(v.edited_sec??v.raw_sec??'')])),checks:current?.confirmations||{},gridEdit:current?.grid||null,vocalEdit:Boolean(current?.vocal_intervals),vocalText:JSON.stringify(current?.vocal_intervals??d.vocals.intervals??[],null,2),note:current?.note||''}))
 }
 useEffect(()=>{let alive=true;call<any>(`/reports/${report.id}/dj`).then(d=>{if(alive)update(d)}).catch(e=>{if(alive)setError(e.message)});return()=>{alive=false}},[report.id])
 async function save(){
  if(!auditionMatches){setError('请先返回报告原曲');return}
  setSaving(true);setError('')
  try{
   const values:Record<string,number>={};for(const [k,v] of Object.entries(anchors)){if(v.trim()){if(!Number.isFinite(Number(v)))throw new Error('边界必须是秒数');values[k]=Number(v)}}
   const payload:any={expected_revision:data.review.revision,source_fingerprint:data.source_fingerprint,anchors:values,confirmations:checks,note}
   if(gridEdit)payload.grid=gridEdit
   if(vocalEdit)payload.vocal_intervals=JSON.parse(vocalText)
   update(await post(`/reports/${report.id}/dj-review`,payload))
  }catch(e){setError((e as Error).message)}finally{setSaving(false)}
 }
 async function makePlan(){
  if(dirty){setError('请先保存上方校准，再生成计划');return}
  setSaving(true);setError('');setPlan(null)
  try{setPlan(await post('/dj/plan',{a_report_id:report.id,b_report_id:next,target_bpm:target?Number(target):null,long_intro_policy:policy||null}))}
  catch(e){setError((e as Error).message)}finally{setSaving(false)}
 }
 if(!data)return <section className="lab-panel"><p>{error||'正在检查接歌所需数据…'}</p></section>
 const duration=data.duration||1,signals=data.signals||{},bars=gridEdit?null:data.grid.bars
 return <div className="lab-dj"><section className="lab-panel"><div className="lab-panel-title"><h2>接歌准备 · DEMO 1.0</h2><div className="lab-actions"><button disabled={busy||saving} onClick={onRun}>计算接歌所需声音特征</button><button onClick={()=>download(`${report.title}-dj-input.json`,JSON.stringify(data,null,2))}>导出接歌输入</button></div></div>
 <p>先确认原曲边界、拍网格和人声，再查看相邻歌曲的接歌计划。秒数均从原文件开头计算；已有分析完整保留。</p>
 {error&&<p className="lab-alert" role="alert">{error}</p>}<DJReadiness data={data}/>
 <CalibrationGuard matches={auditionMatches}><h3>关键边界</h3><p className="lab-muted">段落来源：{data.structure.source}。输入或“取当前试听位置”只修改校准副本，保存后更新接歌输入。</p>
 <div className="lab-table-wrap"><table><thead><tr><th>边界</th><th>模型原始时间</th><th>最近已知首拍</th><th>偏移</th><th>校准秒数</th><th>试听</th></tr></thead><tbody>{Object.entries(data.anchors).map(([k,v]:[string,any])=><tr key={k}><td>{labels[k]}</td><td>{stamp(v.raw_sec)}</td><td>{stamp(v.suggested_sec)}</td><td>{fmt(v.snap_delta_ms,1)} ms</td><td><input aria-label={labels[k]+'秒数'} type="number" min="0" max={duration} step="0.001" value={anchors[k]??''} onChange={e=>{setAnchors({...anchors,[k]:e.target.value});setChecks({...checks,structure:false});setPlan(null)}}/></td><td><button disabled={!anchors[k]} onClick={()=>onSeek(Number(anchors[k]))}>定位</button><button onClick={()=>{setAnchors({...anchors,[k]:cursor.toFixed(3)});setChecks({...checks,structure:false});setPlan(null)}}>取当前试听位置</button></td></tr>)}</tbody></table></div>
 <h3>拍点与小节</h3><p>{data.grid.numerator??'未知'}/{data.grid.denominator??'未知'} 拍 · {data.grid.beats.length} 个拍点 · {data.grid.downbeats.length} 个首拍 · 网格未覆盖开头 {fmt(data.grid.leading_uncovered_sec)} 秒 / 结尾 {fmt(data.grid.trailing_uncovered_sec)} 秒</p>
 <details><summary>逐小节检查与拍网格校准</summary><p>恒速网格适用于已试听确认速度稳定的曲目。第一首拍前的时间会保留为未覆盖区间；生成网格后还需要试听确认。</p>
 <div className="lab-actions"><label>BPM <input aria-label="校准 BPM" type="number" value={bpm} onChange={e=>setBpm(e.target.value)}/></label><label>第一小节首拍（秒）<input aria-label="第一小节首拍" type="number" value={first} onChange={e=>setFirst(e.target.value)}/></label><button onClick={()=>{try{setGridEdit(regularGrid(Number(bpm),Number(first),duration));setChecks({...checks,grid:false});setPlan(null)}catch(e){setError((e as Error).message)}}}>生成待试听的恒速拍网格</button>
 <button onClick={()=>download('dj-grid.json',JSON.stringify(gridEdit||{beats:data.grid.beats,downbeats:data.grid.downbeats,numerator:data.grid.numerator,denominator:data.grid.denominator},null,2))}>导出拍网格</button><label className="lab-button">导入校准拍网格<input type="file" accept=".json" onChange={async e=>{try{const f=e.target.files?.[0];if(!f)return;if(f.size>4*1024*1024)throw new Error('拍网格文件最多 4 MB');setGridEdit(JSON.parse(await f.text()));setChecks({...checks,grid:false});setPlan(null)}catch(e){setError((e as Error).message)}}}/></label></div>
 {gridEdit&&<p className="lab-notice">已准备新的拍网格，保存后生效。<button onClick={()=>{setGridEdit(null);setChecks({...checks,grid:false})}}>恢复原始网格</button></p>}
 <div className="lab-table-wrap"><table><thead><tr><th>小节</th><th>开始 / 结束</th><th>拍数</th><th>人声覆盖</th><th>RMS / 低频</th><th>状态</th></tr></thead><tbody>{(bars||[]).filter((b:any)=>Math.abs(b.start-cursor)<16).map((b:any)=><tr key={b.index}><td>{b.index}</td><td><button onClick={()=>onSeek(b.start)}>{stamp(b.start)} – {stamp(b.end)}</button></td><td>{b.beat_count}</td><td>{b.vocal_ratio==null?'未知':`${fmt(b.vocal_ratio*100,1)}%`}</td><td>{fmt(b.rms_dbfs,1)} / {fmt(b.bands_dbfs?.low,1)} dBFS</td><td>{b.complete?'完整':'拍数或首拍需检查'}</td></tr>)}</tbody></table></div><p className="lab-muted">表格展示当前试听位置前后 16 秒；完整网格可导出。</p></details>
 <h3>人声区间与局部声音</h3><p className="lab-muted">人声来源：{data.vocals.source||'未知'}。先核对分离人声与原曲的时间对齐；50ms 活动曲线用于辅助检查，不代表 50ms 识别精度。</p>
 <Segments title="接歌使用的人声候选" segments={(data.vocals.intervals||[]).map((s:any)=>({...s,label:'人声候选'}))} duration={duration} onSeek={onSeek} collapseList/>
 <Curve title="分离人声强弱 · 50ms" points={series(signals.vocals?.points||[],'rms_dbfs')} duration={duration} cursor={cursor} onSeek={onSeek} unit="dBFS" maxGapSec={.075}/>
 <Curve title="局部响度 · 3 秒未门限窗口" points={series(signals.local_loudness||[],'lufs')} duration={duration} cursor={cursor} onSeek={onSeek} unit="LUFS" maxGapSec={.6}/>
 <Curve title="短时响度 · 400ms 未门限窗口" points={series(signals.momentary_loudness||[],'lufs')} duration={duration} cursor={cursor} onSeek={onSeek} unit="LUFS" maxGapSec={.15}/>
 <Segments title="原曲低于静音阈值的区间" segments={(signals.silence_intervals||[]).map((x:any)=>({...x,label:"低于 -60 dBFS"}))} duration={duration} onSeek={onSeek} collapseList/>
 <details><summary>低、中、高频能量曲线</summary>{[["low","低频"],["mid","中频"],["high","高频"]].map(([k,label])=><Curve key={k} title={label+"强弱"} points={(signals.rms_points||[]).filter((p:any)=>typeof p.bands_dbfs?.[k]==="number").map((p:any)=>({time:p.start,value:p.bands_dbfs[k]}))} duration={duration} cursor={cursor} onSeek={onSeek} unit="滤波后 RMS / dBFS" maxGapSec={.075}/>)}<p className="lab-muted">频带滤波的过渡区会重叠；这些是声音测量，不能直接代表 EQ 应衰减多少。</p></details>
 <p>原曲采样峰值：{fmt(signals.sample_peak_dbfs,2)} dBFS。混音后的真峰值需要实际渲染后测量。</p>
 <details><summary>人声区间人工修订</summary><label><input type="checkbox" checked={vocalEdit} onChange={e=>{setVocalEdit(e.target.checked);setChecks({...checks,vocals:false});setPlan(null)}}/> 使用下方人工区间（秒；空数组表示经试听确认没有人声）</label><textarea aria-label="人工人声区间" value={vocalText} disabled={!vocalEdit} rows={8} style={{width:'100%'}} onChange={e=>{setVocalText(e.target.value);setChecks({...checks,vocals:false});setPlan(null)}}/><p>格式：[{`{"start":1.2,"end":3.4}`} ]，从前到后排列且不重叠。</p></details>
 <h3>保存试听确认</h3><div className="lab-dj-checks">{[['structure','我已试听确认关键段落边界'],['grid','我已试听确认拍点、小节首拍与拍号'],['vocals','我已试听确认人声区间及其与原曲的对齐']].map(([k,label])=><label key={k}><input type="checkbox" checked={Boolean(checks[k])} onChange={e=>{setChecks({...checks,[k]:e.target.checked});setPlan(null)}}/>{label}</label>)}</div>
 <label>校准备注<input aria-label="校准备注" value={note} maxLength={2000} onChange={e=>setNote(e.target.value)}/></label><p><button className="primary" disabled={saving} onClick={save}>{saving?'正在保存…':'保存校准与确认'}</button></p>
 </CalibrationGuard><details><summary>校准历史与数据依据</summary><pre>{JSON.stringify({history:data.review_history||[],current:data.review,source_fingerprint:data.source_fingerprint,source_hashes:data.source_hashes,limitations:data.limitations},null,2)}</pre></details>
 </section><section className="lab-panel"><h3>用本曲作为 A，预览下一次交接</h3><p>计划使用已保存的校准。需要先保存上方修改；未满足条件时仍可查看缺口，不会伪造可执行结果。</p>
 <div className="lab-actions"><label>B 下一首<select aria-label="下一首歌曲" value={next} onChange={e=>{setNext(e.target.value);setPlan(null)}}><option value="">选择曲目</option>{history.filter(h=>h.id!==report.id&&(!h.audio?.sha256||h.audio.sha256!==report.audio.sha256)).map(h=><option key={h.id} value={h.id}>{h.title}</option>)}</select></label>
 <label>目标 BPM<input aria-label="接歌目标 BPM" type="number" placeholder="沿用 A 局部速度" value={target} onChange={e=>{setTarget(e.target.value);setPlan(null)}}/></label>
 <label>长前奏处理<select aria-label="长前奏处理" value={policy} onChange={e=>{setPolicy(e.target.value);setPlan(null)}}><option value="">尚未选择，第三种情况暂不可执行</option><option value="silent_preroll">从头静音预播放，最后四小节混入</option><option value="tail_four_bars">仅播放前奏最后四小节（改变从头播放规则）</option></select></label><button disabled={!next||saving||dirty} onClick={makePlan}>生成接歌计划</button>{dirty&&<p className="lab-notice">校准尚未保存，请先保存再生成计划。</p>}</div></section>
 {plan&&<PlanPreview plan={plan}/>}</div>
}
