import {AudioCache} from '../realtime/cache'
import {scheduleV30Eq} from '../v30/eq'
import {bridgeCurves,type Points} from './policy'
import {referenceCurves,schedule,stemGainPoints} from './automation'
import type {BridgeCase,Mode,PlayerState} from './types'
export class BridgePlayer {
 state:PlayerState={status:'idle',message:'选择一组歌曲，比较两种接法',position:0,mode:'bridge',caseId:''}
 private ctx?:AudioContext;private cache?:AudioCache;private monitor?:AudioWorkletNode;private output?:GainNode
 private initializing?:Promise<void>;private revision=0;private controller?:AbortController
 private sources:AudioBufferSourceNode[]=[];private nodes:AudioNode[]=[];private at=0;private total=0;private raf=0;private disposed=false;private volume=.7
 constructor(private base:URL,private change:(state:PlayerState)=>void){}
 private emit(part:Partial<PlayerState>){this.state={...this.state,...part};this.change(this.state)}
 private init(){
  if(this.initializing)return this.initializing
  this.ctx=new AudioContext({sampleRate:44100})
  const ctx=this.ctx
  this.cache=new AudioCache(ctx,this.base,message=>{if(this.state.status==='loading')this.emit({message})})
  this.initializing=(async()=>{
   await ctx.audioWorklet.addModule(new URL('v3-clock.js',this.base).href)
   if(this.disposed)return
   this.monitor=new AudioWorkletNode(ctx,'v3-clock',{outputChannelCount:[2]})
   this.output=ctx.createGain();this.output.gain.value=this.volume;this.monitor.connect(this.output);this.output.connect(ctx.destination)
   this.monitor.port.onmessage=({data})=>{if(data.planId===String(this.revision))this.emit({peak:data.peak,minimumLimiterGain:data.sessionMinimumLimiterGain})}
  })()
  return this.initializing
 }
 private clear(){
  this.controller?.abort();cancelAnimationFrame(this.raf)
  for(const s of this.sources){s.onended=null;try{s.stop()}catch{}s.disconnect()}
  this.sources=[];for(const n of this.nodes)n.disconnect();this.nodes=[];this.monitor?.port.postMessage({kind:'clear'})
  this.cache?.protected.clear()
 }
 stop(){this.revision++;this.clear();this.emit({status:'idle',position:0,message:'已停止'})}
 async play(c:BridgeCase,mode:Mode){
  if(this.disposed)return
  this.stop();const token=this.revision;this.controller=new AbortController();const signal=this.controller.signal
  this.emit({status:'loading',mode,caseId:c.id,position:0,message:'正在准备同一组分轨…',peak:undefined,minimumLimiterGain:undefined})
  try{
   // Creation/resume is initiated by the user's click before any network wait.
   const initialized=this.init();await this.ctx!.resume();await initialized
   if(token!==this.revision||this.disposed)return
   const entries=Object.entries(c.assets);this.cache!.protected=new Set(entries.map(([,a])=>a.url))
   const buffers=await Promise.all(entries.map(async([key,asset])=>[key,await this.cache!.load(asset,signal)] as const))
   if(token!==this.revision||this.disposed)return
   this.at=this.ctx!.currentTime+.1;this.total=c.pre+c.duration+c.post
   const bus=this.ctx!.createGain();bus.connect(this.monitor!);this.nodes.push(bus)
   schedule(bus.gain,[[0,0],[.02,1],[this.total-.04,1],[this.total,0]],this.at)
   const decoded=Object.fromEntries(buffers)
   const source=(key:keyof typeof c.assets,input:AudioNode,offset:number)=>{
    const s=this.ctx!.createBufferSource();s.buffer=decoded[key];s.connect(input);s.start(this.at+offset);this.sources.push(s)
   }
   if(mode==='bridge'){
    const curves=bridgeCurves(c,c.pre)
    for(const side of ['a','b'] as const){
     const bed=curves[side==='a'?'aBed':'bBed'],voice=curves[side==='a'?'aVoice':'bVoice']
     const master=this.ctx!.createGain(),vocal=this.ctx!.createGain();master.connect(bus);vocal.connect(bus);this.nodes.push(master,vocal)
     schedule(master.gain,bed,this.at,.76);schedule(vocal.gain,stemGainPoints(bed,voice),this.at,.76)
     source(side==='a'?'aMaster':'bMaster',master,side==='a'?0:c.pre)
     source(side==='a'?'aVocal':'bVocal',vocal,side==='a'?0:c.pre)
    }
   }else{
    const curves=referenceCurves(c.pre,c.duration,c.restore)
    const deck=(gain:Points,wetPoints:Points)=>{
     const input=this.ctx!.createGain(),low=this.ctx!.createBiquadFilter(),high=this.ctx!.createBiquadFilter(),mid=this.ctx!.createBiquadFilter(),wet=this.ctx!.createGain(),dry=this.ctx!.createGain(),output=this.ctx!.createGain()
     low.type='lowshelf';low.frequency.value=140;high.type='highshelf';high.frequency.value=3600;mid.type='peaking';mid.frequency.value=1200;mid.Q.value=1.05
     input.connect(low);low.connect(high);high.connect(mid);mid.connect(wet);input.connect(dry);wet.connect(output);dry.connect(output);output.connect(bus)
     schedule(output.gain,gain,this.at,.76);schedule(wet.gain,wetPoints,this.at);schedule(dry.gain,wetPoints.map(([t,v])=>[t,1-v]),this.at)
     this.nodes.push(input,low,high,mid,wet,dry,output);return {input,low,high,mid}
    }
    const a=deck(curves.aGain,curves.aWet),b=deck(curves.bGain,curves.bWet)
    scheduleV30Eq(a,b,this.at+c.pre,c.eq);source('aMaster',a.input,0);source('bMaster',b.input,c.pre)
   }
   this.monitor!.port.postMessage({kind:'arm',events:[c.pre,c.pre+c.duration,this.total].map(t=>({planId:String(token),frame:Math.round((this.at+t)*this.ctx!.sampleRate),phase:t}))})
   this.emit({status:'playing',message:'播放中'});this.tick(token)
  }catch(e){if(token===this.revision&&!this.disposed){this.clear();this.emit({status:'error',message:(e as Error).message})}}
 }
 private tick(token:number){
  if(token!==this.revision||this.disposed)return
  const position=Math.min(this.total,Math.max(0,this.ctx!.currentTime-this.at))
  if(this.ctx!.currentTime>=this.at+this.total+.06){this.clear();this.emit({status:'complete',position:this.total,message:'试听结束，可以换一种接法比较'});return}
  this.emit({position});this.raf=requestAnimationFrame(()=>this.tick(token))
 }
 async pause(){if(this.state.status!=='playing')return;const token=this.revision;await this.ctx!.suspend();if(token===this.revision)this.emit({status:'paused',message:'已暂停'})}
 async resume(){if(this.state.status!=='paused')return;const token=this.revision;await this.ctx!.resume();if(token===this.revision)this.emit({status:'playing',message:'播放中'})}
 setVolume(value:number){this.volume=Math.max(0,Math.min(1,value));if(this.output)this.output.gain.setTargetAtTime(this.volume,this.ctx!.currentTime,.02)}
 dispose(){this.disposed=true;this.stop();this.cache?.dispose();this.monitor?.disconnect();this.output?.disconnect();void this.ctx?.close()}
}
