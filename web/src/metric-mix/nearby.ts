import type {Plan,Track} from '../realtime/planner'
import {planContinuous} from '../continuous/beatAlignment'
import {nativeSegment} from '../continuous/segments'
import type {MetricTransport} from './transport'
import type {Prepared,Method} from './types'
import {canArm} from './plan'
import {buildV30Eq} from '../v30/eq'
export type NearbyOptions={player:MetricTransport;a:Track;b:Track;signal:AbortSignal;prepare:(plan:Plan,signal:AbortSignal)=>Promise<Prepared>;ready?:{result:Prepared;method:Method};onStatus?:(message:string)=>void;leadSeconds?:number}
function wait<T>(operation:Promise<T>,signal:AbortSignal){return new Promise<T>((resolve,reject)=>{
 const cleanup=()=>signal.removeEventListener('abort',abort),abort=()=>{cleanup();reject(signal.reason??new DOMException('已取消','AbortError'))}
 signal.addEventListener('abort',abort,{once:true});operation.then(x=>{cleanup();resolve(x)},e=>{cleanup();reject(e)});if(signal.aborted)abort()
})}
const expired=()=>Object.assign(Error('准备期间接点已过，重新寻找后续接点'),{code:'cue_expired'})
/** Search the nearest short horizon first, retaining the existing planner's
 * quality ranking, bound vocal evidence, local beat gate and dynamic EQ. */
export function nearbyPlan(a:Track,b:Track,position:number,excluded=new Set<string>(),leadSeconds=12){
 const compatible={...b,windows:b.windows.filter(w=>{const v=w.variants[a.id];return v&&v.rate>=.95&&v.rate<=1.05&&v.duration>=1&&v.duration<=32&&[2,4,8].includes(w.bars)})}
 for(const budget of [18,30,60]){
  const search=planContinuous(a,[compatible],position+leadSeconds,{kind:'next',targetId:b.id},new Set(),budget,false)
  for(const plan of search.candidates){if(excluded.has(plan.id))continue;try{return {...plan,v30Eq:buildV30Eq(a,b,plan)}}catch{excluded.add(plan.id)}}
 }
 return null
}
/** One explicit live request: no restart, seek or audition. A missed candidate
 * releases local waiting and is replaced within this bounded request. */
export async function mixNearby(o:NearbyOptions){
 const {player:p,a,b,signal}=o,excluded=new Set<string>()
 const valid=()=>{signal.throwIfAborted();if(p.current?.id!==a.id||!p.playing)throw new DOMException('播放状态已变化，已取消这次混入','AbortError')}
 p.logs.push({kind:'nearby_request',at:new Date().toISOString(),from:a.id,to:b.id,sourcePosition:p.position})
 let lead=o.leadSeconds??12
 let lastError:unknown=Error('附近没有通过拍点、人声和速度检查的接点，请换歌或稍后再试')
 for(let attempt=0;attempt<3;attempt++){
  valid()
  const cached=attempt===0&&o.ready&&o.ready.result.plan.from===a.id&&o.ready.result.plan.to===b.id&&canArm(o.ready.result.plan,a.id,p.position)&&o.ready.result.plan.start<=p.position+lead?o.ready:null
  const plan=cached?null:nearbyPlan(a,b,p.position,excluded,lead)
  if(!cached&&!plan)throw lastError
  const requestedAt=p.position,cue=cached?.result.plan??plan!,controller=new AbortController(),cancel=()=>controller.abort(signal.reason)
  p.logs.push({kind:'nearby_candidate',at:new Date().toISOString(),sourcePosition:p.position,start:cue.start,end:cue.end,leadSeconds:lead,reused:!!cached})
  signal.addEventListener('abort',cancel,{once:true});if(signal.aborted)cancel()
  const timer=setInterval(()=>{
   if(p.current?.id!==a.id||!p.playing)controller.abort(new DOMException('已取消这次混入','AbortError'))
   else if(!canArm(cue,p.current.id,p.position))controller.abort(expired())
  },100)
  try{
   o.onStatus?.(cached?'正在装入已准备好的交接':'已找到附近接点，当前歌曲继续播放，正在准备交接…')
   const result=cached?.result??await wait(o.prepare(plan!,controller.signal),controller.signal)
   valid();controller.signal.throwIfAborted()
   if(result.plan.from!==a.id||result.plan.to!==b.id||Math.abs(result.plan.start-cue.start)>.002)throw Error('交接结果与本次歌曲和接点不一致')
   const method=cached?.method??result.decision.recommended
   if(!result.assets[method]||!result.decision.methods[method]?.eligible)throw Error('该方案没有可用的交接素材')
   await wait(Promise.all([p.cache.load(result.assets[method]!,controller.signal),p.cache.load(nativeSegment(b,result.plan.bEnd).asset,controller.signal)]),controller.signal)
   valid();controller.signal.throwIfAborted()
   if(!canArm(result.plan,p.current!.id,p.position))throw expired()
   await p.arm(result,method,b,controller.signal)
   valid()
   o.onStatus?.('已安排附近接点，将自动混入下一首')
   p.logs.push({kind:'nearby_armed',at:new Date().toISOString(),sourcePosition:p.position,start:result.plan.start,method})
   return {result,method}
  }catch(e){
   valid();if((e as Error).name==='AbortError')throw e
   if((e as {code?:string}).code==='cue_expired')lead=Math.max(lead,Math.min(90,(p.position-requestedAt)*2+5))
   p.logs.push({kind:'nearby_candidate_failed',at:new Date().toISOString(),sourcePosition:p.position,start:cue.start,reason:(e as Error).message})
   lastError=e;if(plan)excluded.add(plan.id)
   o.onStatus?.('这个接点未能及时准备，正在寻找后续可用接点…')
  }finally{clearInterval(timer);signal.removeEventListener('abort',cancel);controller.abort()}
 }
 throw lastError
}
