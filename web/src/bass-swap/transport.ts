import {AudioCache,AudioBufferPool} from '../realtime/cache'
import {scheduleV30Eq} from '../v30/eq'
import {referenceCurves,schedule} from '../vocal-bridge/automation'
import {bassCurves,type Mode,type Timing} from './policy'
import {correction,type Points} from '../melody-overlap/policy'
import type {Asset,Plan} from '../realtime/planner'
export type BassCase={id:string;aTitle:string;bTitle:string;pre:number;post:number;timing:Timing;plan:Plan;planSha256:string;bpm:[number,number];assets:Record<string,Asset>;levels:Record<string,{bassRms:number}>;sourceVerification:unknown}
export type State={status:'idle'|'loading'|'playing'|'complete'|'error';message:string;position:number;caseId:string;mode:Mode}
export class BassPlayer{
 state:State={status:'idle',message:'选择一版开始试听',position:0,caseId:'',mode:'reference'}
 logs:any[]=[];ctx?:AudioContext;cache?:AudioCache
 private ready?:Promise<void>;private monitor?:AudioWorkletNode;private output?:GainNode;private timer?:number
 private nodes:AudioNode[]=[];private sources:AudioBufferSourceNode[]=[];private controller?:AbortController;private revision=0;private dead=false;private at=0;private total=0;private session=''
 constructor(private base:URL,private change:(s:State)=>void,private pool=new AudioBufferPool()){}
 private emit(next:Partial<State>){this.state={...this.state,...next};this.change(this.state)}
 private log(kind:string,data:any={}){this.logs.push({kind,sessionId:this.session,caseId:this.state.caseId,mode:this.state.mode,wallTime:new Date().toISOString(),contextSec:this.ctx?.currentTime,...data})}
 initialize(){
  if(this.ready)return this.ready
  const ctx=this.ctx=new AudioContext({sampleRate:44100,latencyHint:'interactive'})
  this.cache=new AudioCache(ctx,this.base,message=>{if(this.state.status==='loading')this.emit({message})},this.pool)
  this.ready=(async()=>{
   await ctx.audioWorklet.addModule(new URL('v3-clock.js',this.base))
   if(this.dead)return
   this.monitor=new AudioWorkletNode(ctx,'v3-clock',{outputChannelCount:[2]});this.output=ctx.createGain();this.output.gain.value=.7;this.monitor.connect(this.output);this.output.connect(ctx.destination)
   this.monitor.port.onmessage=({data})=>{if(data.planId===String(this.revision))this.log('audio_observation',{...data,basis:'audio render quantum; not speaker latency'})}
   this.timer=window.setInterval(()=>this.tick(),80)
  })()
  return this.ready
 }
 private clear(){
  this.controller?.abort();this.controller=undefined
  for(const s of this.sources){try{s.stop()}catch{}s.disconnect()}
  this.sources=[];for(const n of this.nodes)n.disconnect();this.nodes=[];this.monitor?.port.postMessage({kind:'clear'});this.cache?.protected.clear()
 }
 stop(){if(this.state.status==='playing'||this.state.status==='loading')this.log('bass_stopped',{position:this.state.position});this.revision++;this.clear();this.emit({status:'idle',message:'已停止',position:0})}
 async play(c:BassCase,mode:Mode){
  if(this.dead)return
  this.stop();const token=this.revision;this.session='bass-'+Date.now()+'-'+token;this.controller=new AbortController();const signal=this.controller.signal
  this.emit({status:'loading',message:'正在核验同一组分轨素材…',caseId:c.id,mode,position:0});this.log('bass_requested',{planSha256:c.planSha256})
  try{
   const ready=this.initialize();await this.ctx!.resume();await ready
   if(token!==this.revision||this.dead)return
   const entries=Object.entries(c.assets);this.cache!.protected=new Set(entries.map(([,asset])=>asset.url))
   const decoded=Object.fromEntries(await Promise.all(entries.map(async([key,asset])=>[key,await this.cache!.load(asset,signal)])))
   if(token!==this.revision||this.dead)return
   const ctx=this.ctx!,at=this.at=ctx.currentTime+.1,end=c.pre+c.plan.duration;this.total=end+c.post
   const policy=bassCurves(c.pre,c.plan.duration,c.timing,mode),ref=referenceCurves(c.pre,c.plan.duration,end-Math.min(c.plan.duration,120/c.bpm[0]))
   const bus=ctx.createGain();bus.connect(this.monitor!);this.nodes.push(bus);schedule(bus.gain,[[0,0],[.02,1],[this.total-.04,1],[this.total,0]],at)
   const filters:{a:any[];b:any[]}={a:[],b:[]}
   for(const side of ['a','b'] as const){
    const x=policy[side],gains=[x.rest,correction(x.bass,x.rest)]
    for(const [j,layer] of ['Master','Bass'].entries()){
     const input=ctx.createGain(),low=ctx.createBiquadFilter(),high=ctx.createBiquadFilter(),mid=ctx.createBiquadFilter(),wet=ctx.createGain(),dry=ctx.createGain(),gain=ctx.createGain()
     low.type='lowshelf';low.frequency.value=140;high.type='highshelf';high.frequency.value=3600;mid.type='peaking';mid.frequency.value=1200;mid.Q.value=1.05
     input.connect(low);low.connect(high);high.connect(mid);mid.connect(wet);input.connect(dry);wet.connect(gain);dry.connect(gain);gain.connect(bus)
     const wetPoints=side==='a'?ref.aWet:ref.bWet;schedule(wet.gain,wetPoints,at);schedule(dry.gain,wetPoints.map(([t,v])=>[t,1-v]),at);schedule(gain.gain,gains[j],at,.76)
     this.nodes.push(input,low,high,mid,wet,dry,gain);filters[side].push({low,high,mid})
     const source=(key:string,start:number,duration:number,body=false)=>{
      const s=ctx.createBufferSource(),edge=ctx.createGain();s.buffer=decoded[key];s.connect(edge);edge.connect(input)
      const points:Points=body?[[0,0],[.004,1]]:[[0,1]]
      if(side==='b'&&!body)points.push([Math.max(.004,duration-.004),1],[duration,0])
      schedule(edge.gain,points,at+start);s.start(at+start,0,duration);this.sources.push(s);this.nodes.push(edge)
     }
     if(side==='a')source('a'+layer,0,end)
     else{source('bEntry'+layer,c.pre,c.plan.duration);source('bBody'+layer,end,c.post,true)}
    }
   }
   for(let j=0;j<2;j++)scheduleV30Eq(filters.a[j],filters.b[j],at+c.pre,c.plan.v30Eq!)
   this.log('bass_started',{plan:c.plan,planSha256:c.planSha256,curves:policy,eq:c.plan.v30Eq,nativeHandoffContext:at+end,total:this.total,assets:c.assets,sourceVerification:c.sourceVerification,referenceRendering:'both arms share four-channel master/bass WSOLA entry; native B body at original frozen takeover'})
   this.monitor!.port.postMessage({kind:'arm',events:[c.pre,c.pre+c.timing.duckStart,c.pre+c.timing.swapStart,c.pre+c.timing.swapEnd,end,this.total].map((t,i)=>({planId:String(token),name:['进入交接','A 贝斯渐收位置','贝斯交接起点','贝斯交接首拍','正文接管','试听结束'][i],frame:Math.round((at+t)*ctx.sampleRate)}))})
   this.emit({status:'playing',message:'按固定计划播放中'})
  }catch(e){if(token===this.revision&&!this.dead){this.log('bass_failed',{message:(e as Error).message});this.clear();this.emit({status:'error',message:(e as Error).message})}}
 }
 private tick(){
  if(this.dead||this.state.status!=='playing')return
  const position=Math.min(this.total,Math.max(0,this.ctx!.currentTime-this.at))
  if(this.ctx!.currentTime>=this.at+this.total+.06){this.log('bass_finished',{position:this.total});this.clear();this.emit({status:'complete',message:'本次试听已完整结束',position:this.total});return}
  this.emit({position})
 }
 dispose(){this.dead=true;this.stop();if(this.timer!==undefined)clearInterval(this.timer);this.cache?.dispose();this.monitor?.disconnect();this.output?.disconnect();void this.ctx?.close()}
}
