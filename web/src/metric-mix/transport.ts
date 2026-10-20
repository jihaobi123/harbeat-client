import {AudioCache} from '../realtime/cache'
import {nativeSegment,nativeSegments,SegmentScheduler} from '../continuous/segments'
import type {Track} from '../realtime/planner'
import type {Prepared,Method,PlayingTransition} from './types'
import {canArm,contextForSource,adoptedPosition} from './plan'
type Stream={track:Track;at:number;offset:number;gain:GainNode;sources:Set<AudioBufferSourceNode>;scheduler:SegmentScheduler}
export class MetricTransport{
 ctx=new AudioContext({sampleRate:44100,latencyHint:'interactive'});cache:AudioCache;logs:any[]=[];active:Stream|null=null;transition:PlayingTransition|null=null;status='选择当前歌曲后开始播放';busy=false;buffering=false;paused=false
 private monitor!:AudioWorkletNode;private volume:GainNode;private timer:number;private nodes:AudioNode[]=[];private mixSource:AudioBufferSourceNode|null=null;private dead=false;private revision=0;private load?:AbortController;private ready?:Promise<void>;private streams=new Set<Stream>();private bufferingResume=false;private bufferingOperation=false
 constructor(private base:URL,private changed:()=>void){this.cache=new AudioCache(this.ctx,base,s=>{this.status=s;this.changed()});this.volume=this.ctx.createGain();this.volume.gain.value=.7;this.volume.connect(this.ctx.destination);this.timer=window.setInterval(()=>this.tick(),80)}
 initialize(){return this.ready??=(async()=>{await this.ctx.audioWorklet.addModule(new URL('v3-clock.js',this.base));this.monitor=new AudioWorkletNode(this.ctx,'v3-clock',{outputChannelCount:[2]});this.monitor.connect(this.volume);this.monitor.port.onmessage=({data})=>{this.logs.push({kind:'audio_observation',at:new Date().toISOString(),...data})}})()}
 get current(){return this.active?.track??null}
 get position(){return this.active?Math.min(this.active.track.duration,this.active.offset+Math.max(0,this.ctx.currentTime-this.active.at)):0}
 get playing(){return !!this.active&&this.ctx.state==='running'&&!this.paused}
 get locked(){return !!this.transition&&this.ctx.currentTime>=this.transition.at-.25}
 setVolume(v:number){this.volume.gain.setTargetAtTime(.7*Math.max(0,Math.min(1,v)),this.ctx.currentTime,.02)}
 private log(kind:string,data:any={}){this.logs.push({kind,at:new Date().toISOString(),context:this.ctx.currentTime,...data})}
 private clear(){this.revision++;this.load?.abort();for(const s of this.streams){s.scheduler.dispose();for(const source of s.sources){try{source.stop()}catch{}source.disconnect()}s.gain.disconnect()}this.streams.clear();if(this.mixSource){try{this.mixSource.stop()}catch{}this.mixSource.disconnect();this.mixSource=null}for(const n of this.nodes)n.disconnect();this.nodes=[];this.active=null;this.transition=null;this.cache.protected.clear();this.monitor?.port.postMessage({kind:'clear'});this.buffering=false;this.bufferingResume=false}
 private stream(track:Track,offset:number,at:number,buffer:AudioBuffer,fade=false):Stream{
  const gain=this.ctx.createGain();gain.gain.value=.60;gain.connect(this.monitor);const sources=new Set<AudioBufferSourceNode>();let stream:Stream
  const scheduler=new SegmentScheduler(track,at,offset,{now:()=>this.ctx.currentTime,load:(asset,signal)=>this.cache.load(asset,signal),changed:()=>this.pins(),scheduled:e=>this.log('native_chunk',{track:track.id,...e}),schedule:(pcm,start,sourceOffset,duration,edge)=>{
   const src=this.ctx.createBufferSource(),eg=this.ctx.createGain();src.buffer=pcm;src.connect(eg);eg.connect(gain);eg.gain.value=1
   if(edge){eg.gain.setValueAtTime(0,start);eg.gain.linearRampToValueAtTime(1,start+(fade?.008:.004))}
   src.onended=()=>{src.disconnect();eg.disconnect();sources.delete(src)};src.start(start,sourceOffset,duration);sources.add(src);return()=>{try{src.stop()}catch{}src.disconnect();eg.disconnect();sources.delete(src)}
  }});stream={track,at,offset,gain,sources,scheduler};this.streams.add(stream);scheduler.begin(buffer);return stream
 }
 private pins(){const pins=new Set<string>();for(const s of this.streams)for(const p of s.scheduler.pins)pins.add(p);if(this.transition){const a=this.transition.result.assets[this.transition.method];if(a)pins.add(a.url)}this.cache.protected=pins}
 async start(track:Track,offset=0){
  if(!Number.isFinite(offset)||offset<0||offset>=track.duration-.1)throw Error('播放位置超出歌曲范围')
  this.clear();const rev=this.revision;this.busy=true;this.paused=false;this.load=new AbortController();this.changed()
  try{await this.initialize();const segment=nativeSegment(track,offset),buffer=await this.cache.load(segment.asset,this.load.signal);if(rev!==this.revision||this.dead)return false;await this.ctx.resume();if(rev!==this.revision||this.dead)return false;const at=this.ctx.currentTime+.12;this.active=this.stream(track,offset,at,buffer);this.status='正在播放原曲';this.log('track_start',{track:track.id,offset,contextStart:at});this.pins();return true}finally{if(rev===this.revision){this.busy=false;this.changed()}}
 }
 async arm(result:Prepared,method:Method,b:Track){
  const a=this.active;if(!a||b.id!==result.plan.to||!canArm(result.plan,a.track.id,this.position)||this.transition)throw Error('这个接点已过或正在交接，请重新准备')
  if(!result.decision.methods[method]?.eligible||!result.assets[method])throw Error('该方案未通过本轮条件检查')
  const rev=this.revision;this.busy=true;this.load=new AbortController();this.changed()
  try{
   const [buffer,body]=await Promise.all([this.cache.load(result.assets[method]!,this.load.signal),this.cache.load(nativeSegment(b,result.plan.bEnd).asset,this.load.signal)])
   if(rev!==this.revision||this.dead)return
   if(!canArm(result.plan,a.track.id,this.position))throw Error('准备完成时接点已经过去，请重新准备')
   const at=contextForSource(a.at,a.offset,result.plan.start),end=at+result.plan.duration
   // One clock: original A -> rendered overlap -> native B at its frozen endpoint.
   const src=this.ctx.createBufferSource(),edge=this.ctx.createGain();src.buffer=buffer;src.connect(edge);edge.connect(this.monitor);edge.gain.value=1;edge.gain.setValueAtTime(0,at);edge.gain.linearRampToValueAtTime(1,at+.004);edge.gain.setValueAtTime(1,end);edge.gain.linearRampToValueAtTime(0,end+.008)
   a.gain.gain.setValueAtTime(.60,at);a.gain.gain.linearRampToValueAtTime(0,at+.004)
   src.onended=()=>{src.disconnect();edge.disconnect();if(this.mixSource===src)this.mixSource=null};src.start(at);this.nodes.push(edge);this.mixSource=src;this.transition={result,method,b,at,end};this.stream(b,result.plan.bEnd,end,body,true)
   const events=[{name:'交接开始',frame:Math.round(at*this.ctx.sampleRate)},{name:'B正文接管',frame:Math.round(end*this.ctx.sampleRate)}].map(e=>({...e,planId:result.id,requestId:method}));this.monitor.port.postMessage({kind:'arm',events});this.log('plan_scheduled',{method,plan:result.plan,policyVersion:result.policyVersion,codeVersion:result.codeVersion,decision:result.decision,metrics:result.metrics,asset:result.assets[method],at,end});this.status='已安排 '+result.decision.methods[method].name;this.pins()
  }finally{if(rev===this.revision){this.busy=false;this.changed()}}
 }
 async audition(result:Prepared,method:Method,a:Track,b:Track){
  const asset=result.assets[method];if(!asset||!result.decision.methods[method]?.eligible||result.plan.from!==a.id||result.plan.to!==b.id)throw Error('试听方案与歌曲不一致')
  this.clear();const rev=this.revision,offset=Math.max(0,result.plan.start-4);this.busy=true;this.load=new AbortController();this.status='正在准备完整试听素材…';this.changed()
  try{
   await this.initialize();if(rev!==this.revision||this.dead)return
   const aChunks=nativeSegments(a).filter(s=>s.end>offset&&s.start<result.plan.start+.008),bChunks=nativeSegments(b).filter(s=>s.end>result.plan.bEnd).slice(0,2),assets=[...aChunks,...bChunks].map(s=>s.asset).concat(asset)
   this.cache.protected=new Set(assets.map(a=>a.url));await Promise.all(assets.map(a=>this.cache.load(a,this.load!.signal)))
   if(rev!==this.revision||this.dead)return
   const started=await this.start(a,offset);if(started)await this.arm(result,method,b)
  }finally{if(rev===this.revision){this.busy=false;this.changed()}}
 }
 private tick(){
  if(this.dead||!this.active)return
  const now=this.ctx.currentTime,t=this.transition
  if(t&&now>=t.at+.008&&this.streams.has(this.active)){this.active.scheduler.dispose();for(const source of this.active.sources){try{source.stop()}catch{}source.disconnect()}this.active.sources.clear();this.streams.delete(this.active)}
  if(t&&now>=t.end){const old=this.active,body=[...this.streams].find(s=>s.track.id===t.b.id&&s.at===t.end);if(!body){this.status='正文准备异常，请停止后重试';this.pause();return}this.active=body;old.scheduler.dispose();for(const s of old.sources){try{s.stop()}catch{}s.disconnect()}old.sources.clear();old.gain.disconnect();this.streams.delete(old);this.transition=null;this.status='已进入 '+body.track.title;this.log('handoff_complete',{track:body.track.id,sourceOffset:adoptedPosition(t.result.plan,t.end,now),method:t.method});this.pins()}
  for(const s of this.streams)s.scheduler.pump()
  const starving=[...this.streams].find(s=>s.scheduler.error||s.scheduler.late||now>=s.scheduler.deadline-.12)
  if(starving&&!this.bufferingOperation&&this.playing){this.bufferingOperation=true;this.buffering=true;this.bufferingResume=true;void this.ctx.suspend().then(()=>{this.status='网络准备中，已暂停时间轴';this.changed()}).finally(()=>this.bufferingOperation=false)}
  if(this.buffering&&!this.bufferingOperation){
   for(const s of this.streams)if(s.scheduler.error)s.scheduler.retry()
   if([...this.streams].every(s=>!s.scheduler.error&&!s.scheduler.late&&this.ctx.currentTime<s.scheduler.deadline-.12)){this.buffering=false;if(this.bufferingResume&&!this.paused){this.bufferingOperation=true;void this.ctx.resume().finally(()=>{this.bufferingOperation=false;this.changed()})}}
   if([...this.streams].some(s=>s.scheduler.late))this.status='音频准备晚于接点，请停止后重试'
  }
  if(this.position>=this.active.track.duration-.03&&!this.transition&&!this.paused){this.status='播放结束，请选择下一首';this.pause()}
  this.changed()
 }
 pause(){this.paused=true;this.bufferingResume=false;void this.ctx.suspend();this.log('pause');this.changed()}
 async resume(){this.paused=false;this.bufferingResume=true;if(!this.buffering)await this.ctx.resume();this.log('resume');this.changed()}
 stop(){this.log('stop');this.clear();this.busy=false;this.paused=false;this.status='已停止';this.changed()}
 async seek(offset:number){const track=this.current;if(!track)return;await this.start(track,offset)}
 export(){return {schema:'harbeat.metric-mix-session.v1',sampleRate:this.ctx.sampleRate,logs:this.logs,limitations:['Render-quantum timings are not device/Bluetooth latency','Rule scores are provisional,not listening success probabilities']}}
 dispose(){this.dead=true;this.clear();clearInterval(this.timer);this.cache.dispose();this.monitor?.disconnect();this.volume.disconnect();void this.ctx.close()}
}
