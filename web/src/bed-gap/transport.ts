import {AudioCache,AudioBufferPool} from '../realtime/cache'
import {gapCurves,type Mode} from './policy'
import type {Asset,Plan} from '../realtime/planner'
import {makeGapGraph} from './graph'
export type BedGapCase={id:string;aTitle:string;bTitle:string;pre:number;post:number;pauseSeconds:number;pauseEdgeSeconds:number;pauseEvidence:any;plan:Plan;planSha256:string;bpm:[number,number];assets:Record<string,Asset>;sourceVerification:unknown;features:any}
export type State={status:'idle'|'loading'|'playing'|'complete'|'error';message:string;position:number;caseId:string;mode:Mode;roundId?:string;letter?:string}
const assetKeys=['aMaster','aVocal','bEntryMaster','bEntryVocal','bBodyMaster','bBodyVocal'] as const
function validateCase(c:BedGapCase){
 gapCurves(c.pre,c.plan.duration,c.pauseSeconds,c.pauseEdgeSeconds,'natural')
 if(c.pauseEdgeSeconds!==.005||Math.abs(c.pauseSeconds-30/c.bpm[0])>1e-9||c.pauseEvidence?.voicePolicy!=='original-linear-fades')throw Error('本轮仅允许半拍伴奏留白，人声沿用原曲线')
 if(![c.plan.start,c.plan.end,c.plan.rate,c.plan.window.start,c.plan.window.end,...c.bpm].every(Number.isFinite)||c.plan.rate<=0||c.bpm.some(x=>x<=0))throw Error('Invalid frozen clock')
 if(c.post<=c.pauseEdgeSeconds||!Number.isFinite(c.post)||Object.keys(c.assets).length!==6||assetKeys.some(k=>!c.assets[k])||!c.plan.v30Eq||Math.abs(c.plan.end-c.plan.start-c.plan.duration)>.002||Math.abs((c.plan.window.end-c.plan.window.start)/c.plan.rate-c.plan.duration)>.002)throw Error('Source clips differ from frozen plan')
}
export class BedGapPlayer{
 readonly recordId=crypto.randomUUID()
 state:State={status:'idle',message:'选择一版开始试听',position:0,caseId:'',mode:'natural'}
 logs:any[]=[];ctx?:AudioContext;cache?:AudioCache
 private ready?:Promise<void>;private monitor?:AudioWorkletNode;private output?:GainNode;private timer?:number
 private nodes:AudioNode[]=[];private sources:AudioBufferSourceNode[]=[];private controller?:AbortController;private revision=0;private dead=false;private at=0;private total=0;private session='';private blind:{roundId?:string;letter?:string}={}
 private onset?:{revision:number;frame:number;requestedAt:number}
 constructor(private base:URL,private change:(s:State)=>void,private pool=new AudioBufferPool()){}
 private emit(next:Partial<State>){this.state={...this.state,...next};this.change(this.state)}
 private log(kind:string,data:any={}){this.logs.push({kind,...this.blind,sessionId:this.session,caseId:this.state.caseId,mode:this.state.mode,wallTime:new Date().toISOString(),contextSec:this.ctx?.currentTime,...data})}
 initialize(){
  if(this.ready)return this.ready
  const ctx=this.ctx=new AudioContext({sampleRate:44100,latencyHint:'interactive'})
  this.cache=new AudioCache(ctx,this.base,message=>{if(this.state.status==='loading')this.emit({message})},this.pool)
  this.ready=(async()=>{
   await ctx.audioWorklet.addModule(new URL('vocal-echo-clock.js',this.base))
   if(this.dead)return
   this.monitor=new AudioWorkletNode(ctx,'vocal-echo-clock',{outputChannelCount:[2]});this.output=ctx.createGain();this.output.gain.value=.7;this.monitor.connect(this.output);this.output.connect(ctx.destination)
   this.monitor.port.onmessage=({data})=>{
    if(this.dead||data.planId!==String(this.revision))return
    this.log('audio_observation',{...data,basis:'audio render quantum; not speaker latency'})
    if(this.onset?.revision===this.revision&&data.name==='试听开始'&&data.frame===this.onset.frame&&data.observedFrame>=data.frame&&this.state.status==='loading'){
     this.onset=undefined
     this.log('gap_render_started',{actualStartContext:this.at,renderFrame:data.frame,observedFrame:data.observedFrame,basis:'audio render quantum; not speaker latency'})
     this.emit({status:'playing',message:'按固定计划播放中'})
    }
   }
   this.timer=window.setInterval(()=>this.tick(),80)
  })()
  return this.ready
 }
 private clear(){
  this.onset=undefined
  this.controller?.abort();this.controller=undefined
  for(const s of this.sources){try{s.stop()}catch{}s.disconnect()}
  this.sources=[];for(const n of this.nodes)n.disconnect();this.nodes=[];this.monitor?.port.postMessage({kind:'clear'});this.cache?.protected.clear()
 }
 stop(){if(this.state.status==='playing'||this.state.status==='loading')this.log('gap_stopped',{position:this.state.position});this.revision++;this.clear();this.emit({status:'idle',message:'已停止',position:0})}
 async play(c:BedGapCase,mode:Mode,meta:{roundId:string;letter:string}={roundId:'',letter:''}){
  if(this.dead)return
  this.stop();const token=this.revision;this.session='bed-gap-'+Date.now()+'-'+token;this.blind={...meta};this.controller=new AbortController();const signal=this.controller.signal
  this.emit({status:'loading',message:'正在核验同一组分轨素材…',caseId:c.id,mode,...meta,position:0});this.log('gap_requested',{planSha256:c.planSha256})
  try{
   validateCase(c)
   const ready=this.initialize();await this.ctx!.resume();await ready
   if(token!==this.revision||this.dead)return
   const entries=Object.entries(c.assets);this.cache!.protected=new Set(entries.map(([,asset])=>asset.url))
   const decoded=Object.fromEntries(await Promise.all(entries.map(async([key,asset])=>[key,await this.cache!.load(asset,signal)])))
   if(token!==this.revision||this.dead)return
   for(const key of assetKeys){const buffer=decoded[key],duration=key.startsWith('a')?c.pre+c.plan.duration:key.startsWith('bEntry')?c.plan.duration:c.post;if(buffer.numberOfChannels!==2||Math.abs(buffer.length-Math.round(duration*this.ctx!.sampleRate))>1)throw Error('人声分轨与固定播放时间轴不一致')}
   const ctx=this.ctx!;if(ctx.state!=='running')throw Error('音频暂未启动，请再次点击试听重试');const at=this.at=ctx.currentTime+.1,end=c.pre+c.plan.duration;this.total=end+c.post
   const policy=gapCurves(c.pre,c.plan.duration,c.pauseSeconds,c.pauseEdgeSeconds,mode)
   const graph=makeGapGraph(ctx,this.monitor!,decoded,c,mode,at);this.nodes.push(...graph.nodes);this.sources.push(...graph.sources)
   this.log('gap_started',{plan:c.plan,planSha256:c.planSha256,treatment:policy,pauseSeconds:c.pauseSeconds,pauseEdgeSeconds:c.pauseEdgeSeconds,eq:c.plan.v30Eq,audioContextState:ctx.state,actualStartContext:at,nativeHandoffContext:at+end,total:this.total,assets:c.assets,sourceVerification:c.sourceVerification,pauseEvidence:c.pauseEvidence,referenceRendering:'Exact original master/vocal clips; original vocal gains preserved via signed correction; only a local final-halfbeat accompaniment gap changes'})
   const markers=[{t:0,name:'试听开始'},{t:c.pre,name:'位置 1'},{t:end-c.pauseSeconds-c.pauseEdgeSeconds,name:'位置 2'},{t:end-c.pauseSeconds,name:'位置 3'},{t:end,name:'位置 4'},{t:end+c.pauseEdgeSeconds,name:'位置 5'},{t:this.total,name:'试听结束'}]
   this.onset={revision:token,frame:Math.round(at*ctx.sampleRate),requestedAt:Date.now()}
   this.monitor!.port.postMessage({kind:'arm',events:markers.map(({t,name})=>({planId:String(token),name,frame:Math.round((at+t)*ctx.sampleRate)}))})
  }catch(e){if(token===this.revision&&!this.dead){this.log('gap_failed',{message:(e as Error).message});this.clear();this.emit({status:'error',message:(e as Error).message})}}
 }
 private tick(){
  if(this.dead)return
  if(this.state.status==='loading'&&this.onset&&Date.now()-this.onset.requestedAt>5000){
   const message='音频未能开始，请再次点击试听重试'
   this.log('gap_failed',{message,reason:'render-onset-timeout',audioContextState:this.ctx?.state,scheduledContext:this.at,observedContext:this.ctx?.currentTime});this.revision++;this.clear();this.emit({status:'error',message});return
  }
  if(this.state.status!=='playing')return
  const position=Math.min(this.total,Math.max(0,this.ctx!.currentTime-this.at))
  if(this.ctx!.currentTime>=this.at+this.total+.06){this.log('gap_finished',{position:this.total});this.clear();this.emit({status:'complete',message:'本次试听已完整结束',position:this.total});return}
  this.emit({position})
 }
 dispose(){this.dead=true;this.stop();if(this.timer!==undefined)clearInterval(this.timer);this.cache?.dispose();this.monitor?.disconnect();this.output?.disconnect();void this.ctx?.close()}
}
