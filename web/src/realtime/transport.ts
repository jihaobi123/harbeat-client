import {planAutomatic} from '../continuous/automaticPlan'
import {nativeSegment,SegmentScheduler} from '../continuous/segments'
import type {OverlapPlan} from '../vocal-overlap/planner'
import {scheduleV30Eq} from '../v30/eq'
import {scheduleAutomation} from '../phrase/schedule'
import {buildDecisionTrace} from './trace'
import {SessionWriter,saveSession} from './sessionStore'
import {DECISION_POLICY} from './decision'
import {AudioCache,type AudioBufferPool} from './cache'
import {planNext,RequestGate,Track,Intent,Plan} from './planner'
export type Log=Record<string,any>
export type ComparisonRun={experimentId:string;arm:'baseline'|'variant';midDb:-5|-8;[key:string]:unknown}
type Deck={stream?:SegmentScheduler;track:Track;sources:AudioBufferSourceNode[];nodes:AudioNode[];gain:GainNode;dry:GainNode;wet:GainNode;low:BiquadFilterNode;high:BiquadFilterNode;mid:BiquadFilterNode;at:number;offset:number;headEnd?:number;bodyOffset?:number;rate?:number}
type Pending={automatic?:boolean;plan:Plan;deck:Deck;start:number;end:number;id:string;committed:boolean;requestId:string}
export class LiveTransport{
 private automaticRequestId:string|null=null
 private automaticPrepared:{source:Deck;targetId:string;result:ReturnType<typeof planAutomatic>}|null=null
 get automaticStart(){return this.automaticPrepared?.source===this.active?this.automaticPrepared.result.best?.start??null:null}
 cancelAutomatic(){if((this.pending?.automatic||this.automaticRequestId!==null&&this.automaticRequestId===this.currentRequestId)&&!this.gate.locked)this.cancel()}
 buffering=false;private bufferSuspend:Promise<void>|null=null;private bufferResume=false;private startLoad:AbortController|null=null;private requestLoad:AbortController|null=null;private prepareLoad:AbortController|null=null;private prepareSequence=0;private preparedPins=new Set<string>();private requestPins=new Set<string>();private startPins=new Set<string>();
 private comparisonId:string|null=null;private comparisonMode=false;private comparisonEnd:number|null=null;private comparisonMidDb=-5;
 persistenceStatus='会话尚未保存';private recorder:SessionWriter|null=null;private flushSession=()=>{void this.recorder?.flush()};
 ctx:AudioContext;cache:AudioCache;gate=new RequestGate();logs:Log[]=[];active:Deck|null=null;pending:Pending|null=null;status='选择歌曲后开始播放';lastPlan:Plan|null=null;lastSearch:any=null;paused=false;busy=false;private monitor!:AudioWorkletNode;private volume:GainNode;private timer:number;private starting=0;private autoTried=false;private base:URL;private dead=false;private deferredDeadline=0;private requestSequence=0;private currentRequestId:string|null=null;private deferredRequestId:string|null=null;private terminalRequests=new Set<string>();readonly sessionId=`live-${Date.now()}-${Math.random().toString(36).slice(2,10)}`
 constructor(public tracks:Track[],private update:()=>void,base:URL,private options:{planner?:typeof planNext;autoNext?:boolean;prewarm?:boolean;noPlanMessage?:string;policyVersion?:string;release?:{version:string;id:string;acceptedArm:string;acceptedSourceCommit:string};audioPool?:AudioBufferPool}={}){this.base=base;this.ctx=new AudioContext({sampleRate:44100,latencyHint:'interactive'});this.volume=this.ctx.createGain();this.volume.gain.value=.85;this.volume.connect(this.ctx.destination);this.cache=new AudioCache(this.ctx,base,s=>{if((this.busy||!this.active)&&!this.buffering){this.status=s;this.update()}},options.audioPool);this.timer=window.setInterval(()=>this.tick(),80);if(typeof indexedDB!=='undefined'){this.recorder=new SessionWriter(()=>this.export(),saveSession,status=>{this.persistenceStatus=status;if(!this.dead)this.update()});window.addEventListener('pagehide',this.flushSession)}this.ctx.onstatechange=()=>{this.log('context_state',{state:this.ctx.state});this.update()}}
 async initialize(){await this.ctx.audioWorklet.addModule(new URL('v3-clock.js',this.base));this.monitor=new AudioWorkletNode(this.ctx,'v3-clock',{outputChannelCount:[2]});this.monitor.connect(this.volume);this.monitor.port.onmessage=({data})=>{this.log('audio_observation',{...data,plannedContextSec:data.frame/this.ctx.sampleRate,observedContextSec:data.observedFrame/this.ctx.sampleRate,observationDeltaMs:(data.observedFrame-data.frame)/this.ctx.sampleRate*1000,messageReceivedContextSec:this.ctx.currentTime,basis:'Audio-thread render quantum observation; not measured source onset, device output or Bluetooth latency'});this.sync();this.update()}}
 log(kind:string,data:Log={}){this.logs.push(JSON.parse(JSON.stringify({kind,sessionId:this.sessionId,sequence:this.logs.length+1,wallTime:new Date().toISOString(),contextSec:this.ctx.currentTime,...data})));if(this.recorder){if(['request_received','plan_scheduled','audio_observation','request_outcome','track_stop'].includes(kind))void this.recorder.flush();else this.recorder.queue()}}
 private outcome(requestId:string|null,outcome:string,reason:string,extra:Log={}){if(!requestId||this.terminalRequests.has(requestId))return;this.terminalRequests.add(requestId);this.log('request_outcome',{requestId,outcome,reason,...extra})}
 private auditSearch(requestId:string,phase:string,result:ReturnType<typeof planNext>,position:number,budget:number){
  const ranked=result.candidates.map((p,rank)=>({rank:rank+1,id:p.id,to:p.to,windowId:p.window.id,start:p.start,end:p.end,score:p.score,prepared:p.prepared,scoreComponents:p.decision?.score.components,reason:p.reason,localEvidence:p.evidence,...((p as OverlapPlan).vocalOverlap?{vocalOverlap:(p as OverlapPlan).vocalOverlap}:{})}))
  this.log('decision_search',{requestId,phase,sourcePosition:position,planningPosition:'planningPosition' in result?result.planningPosition:position,remainingBudgetSec:budget,result:{candidateCount:ranked.length,selectedId:result.best?.id||null,selectedAdjustment:result.best?.v30Tune||null,selectedEqMode:result.best?.v30Eq?'dynamic':'fixed',...((result.best as OverlapPlan|null)?.vocalOverlap?{selectedVocalOverlap:(result.best as OverlapPlan).vocalOverlap}:{}),candidates:ranked,exclusions:result.exclusions,rejected:result.rejected},policyVersion:this.options.policyVersion||DECISION_POLICY.version})
 }

 get position(){if(!this.active)return 0;return Math.min(this.active.track.duration,this.active.offset+Math.max(0,this.ctx.currentTime-this.active.at))}
 get current(){return this.active?.track||null}
 get playing(){return !!this.active&&!this.paused&&this.ctx.state==='running'}
 setVolume(value:number){this.volume.gain.setTargetAtTime(Math.max(0,Math.min(1,value)),this.ctx.currentTime,.015)}
 private hold(p:AudioParam,value:number){const now=this.ctx.currentTime;if(p.cancelAndHoldAtTime)p.cancelAndHoldAtTime(now);else p.cancelScheduledValues(now);p.linearRampToValueAtTime(value,now+.02)}
 private graph(track:Track,at:number,offset:number):Deck{
  const input=this.ctx.createGain(),low=this.ctx.createBiquadFilter(),high=this.ctx.createBiquadFilter(),mid=this.ctx.createBiquadFilter(),wet=this.ctx.createGain(),dry=this.ctx.createGain(),gain=this.ctx.createGain()
  low.type='lowshelf';low.frequency.value=140;high.type='highshelf';high.frequency.value=3600;mid.type='peaking';mid.frequency.value=1200;mid.Q.value=1.05
  input.connect(low);low.connect(high);high.connect(mid);mid.connect(wet);input.connect(dry);wet.connect(gain);dry.connect(gain);gain.connect(this.monitor);wet.gain.value=0;dry.gain.value=1;gain.gain.value=.76
  return {track,sources:[],nodes:[input,low,high,mid,wet,dry,gain],gain,wet,dry,low,high,mid,at,offset}
 }
 private source(d:Deck,buffer:AudioBuffer,at:number,offset:number,until?:number,edge=false,span?:number){
  const source=this.ctx.createBufferSource(),gain=this.ctx.createGain();source.buffer=buffer;source.connect(gain);gain.connect(d.nodes[0]);if(span===undefined)source.start(at,offset);else source.start(at,offset,span)
  if(until){gain.gain.setValueAtTime(1,Math.max(at,until-.004));gain.gain.linearRampToValueAtTime(0,until);source.stop(until)}else if(edge){gain.gain.setValueAtTime(0,at);gain.gain.linearRampToValueAtTime(1,at+.004)}
  d.sources.push(source);d.nodes.push(gain)
  const release=()=>{try{source.disconnect();gain.disconnect();source.buffer=null}catch{}d.sources=d.sources.filter(x=>x!==source);d.nodes=d.nodes.filter(x=>x!==gain)}
  source.onended=release;return release
 }
 private nativeSource(d:Deck,buffer:AudioBuffer,at:number,offset:number,edge=false){
  if(!d.track.audioSegments){this.source(d,buffer,at,offset,undefined,edge);return}
  d.stream=new SegmentScheduler(d.track,at,offset,{now:()=>this.ctx.currentTime,load:(asset,signal)=>this.cache.load(asset,signal),schedule:(b,t,o,duration,first)=>this.source(d,b,t,o,undefined,first,duration),changed:()=>{this.protected();if(this.buffering)this.checkSegments();this.update()},scheduled:event=>this.log('native_segment_scheduled',{track:d.track.id,sourceStart:event.sourceStart,sourceEnd:event.sourceEnd,scheduledContextSec:event.at,assetUrl:event.asset.url,assetSha256:event.asset.sha256})})
  d.stream.begin(buffer,edge)
 }
 private retire(d:Deck,fade=true){d.stream?.dispose();const now=this.ctx.currentTime;if(fade)this.hold(d.gain.gain,0);for(const source of d.sources){try{source.stop(now+(fade?.025:0))}catch{}}setTimeout(()=>d.nodes.forEach(n=>{try{n.disconnect()}catch{}}),80)}
 private protected(){
  const decks=[this.active,this.pending?.deck].filter(Boolean) as Deck[]
  this.cache.protected=new Set([...decks.flatMap(d=>d.stream?[...d.stream.pins]:[d.track.native.url]),...(this.pending?[this.pending.plan.asset.url]:[]),...this.preparedPins,...this.requestPins,...this.startPins])
 }
 async start(id:string,offset=0,preservePause=false){
  const token=++this.starting;this.stop(false);const controller=new AbortController();this.startLoad=controller;this.busy=true;this.paused=preservePause;this.status='正在准备原曲…';this.update()
  try{
   if(preservePause)await this.ctx.suspend();else await this.ctx.resume()
   if(token!==this.starting||this.dead)return
   const track=this.tracks.find(t=>t.id===id);if(!track)throw new Error('歌曲不存在')
   const sourceOffset=Math.max(0,Math.min(track.duration-1,offset)),asset=track.audioSegments?nativeSegment(track,sourceOffset).asset:track.native
   this.startPins=new Set([asset.url]);this.protected();const buffer=await this.cache.load(asset,controller.signal)
   if(token!==this.starting||this.dead)return
   const at=this.ctx.currentTime+.08;this.active=this.graph(track,at,sourceOffset);this.nativeSource(this.active,buffer,at,sourceOffset);this.active.gain.gain.setValueAtTime(0,at);this.active.gain.gain.linearRampToValueAtTime(.76,at+.02)
   this.status=this.paused?'已暂停，交接时钟同时暂停':'正在播放';this.autoTried=false;this.log('track_start',{track:track.id,sourceOffset,scheduledAt:at,assetSha256:asset.sha256});this.startPins.clear();this.protected()
  }catch(error){if(token===this.starting&&!controller.signal.aborted){this.status=(error as Error).message;throw error}}
  finally{if(token===this.starting){this.startLoad=null;this.startPins.clear();this.busy=false;this.protected();this.update();if(this.active)void this.prewarm()}}
 }
 stop(invalidate=true){this.startLoad?.abort();this.startLoad=null;this.requestLoad?.abort();this.requestLoad=null;this.cancelPreparation();this.requestPins.clear();this.startPins.clear();this.buffering=false;this.bufferSuspend=null;this.bufferResume=false;this.comparisonMode=false;this.comparisonEnd=null;this.comparisonMidDb=-5;this.outcome(this.currentRequestId,'stopped','播放停止或重新开始，撤销尚未完成的混音');this.outcome(this.deferredRequestId,'stopped','播放停止，清除等待中的请求');this.currentRequestId=null;this.deferredRequestId=null;if(invalidate)this.starting++;this.gate.reset();if(this.pending)this.retire(this.pending.deck);if(this.active)this.retire(this.active);this.pending=null;this.active=null;this.busy=false;this.paused=false;this.autoTried=false;this.monitor?.port.postMessage({kind:'clear'});this.cache.protected.clear();this.status='已停止';this.log('stop');this.update()}
 async togglePause(){
  if(!this.active)return
  const token=this.starting;this.paused=!this.paused
  if(this.paused){await this.ctx.suspend();if(token!==this.starting)return;this.status='已暂停，交接时钟同时暂停'}
  else{for(const d of [this.active,this.pending?.deck])d?.stream?.retry();this.checkSegments();if(!this.buffering)await this.ctx.resume();if(token!==this.starting)return;if(this.paused)await this.ctx.suspend();else this.status=this.buffering?'正在缓冲整曲音频…':'继续播放'}
  this.log('pause',{paused:this.paused});this.update()
 }
 async seek(position:number){if(!this.active)return;const id=this.active.track.id,pause=this.paused;this.log('seek',{position});await this.start(id,position,pause)}
 cancelPreparation(){this.automaticPrepared=null;this.prepareSequence++;this.prepareLoad?.abort();this.prepareLoad=null;this.preparedPins.clear();this.protected()}
 async prepareNext(trackId:string,options:{automatic?:boolean}={}){
  this.cancelPreparation();const active=this.active;if(!active)throw new Error('请先播放歌曲')
  const token=this.prepareSequence,controller=new AbortController();this.prepareLoad=controller
  const check=()=>{if(controller.signal.aborted||token!==this.prepareSequence||this.active!==active||this.dead)throw new DOMException('下一首准备已取消','AbortError')}
  try{
   const planner=this.options.planner||planNext,target=this.tracks.find(t=>t.id===trackId)
   if(!target)throw new Error('歌曲不存在')
   for(let attempt=0;attempt<3;attempt++){
    const result=options.automatic?planAutomatic(planner,active.track,this.tracks,this.position,{kind:'next',targetId:trackId},this.cache.ready):
     {...planner(active.track,this.tracks,this.position,{kind:'next',targetId:trackId},this.cache.ready,30,false),planningPosition:this.position}
    const plan=result.best
    if(!plan)throw new Error(options.automatic?'这首歌在剩余播放范围内没有可靠接点，正在寻找其他歌曲。':this.options.noPlanMessage||'当前时间附近没有符合要求的交接窗口，可以稍后再试或换一首')
    const body=nativeSegment(target,plan.window.end).asset
    this.preparedPins=new Set([target.native.url,plan.asset.url,body.url]);this.protected();this.log('next_preparation_started',{trackId,from:active.track.id,candidateId:plan.id,automatic:!!options.automatic,sourcePosition:this.position,planningPosition:result.planningPosition,plannedStart:plan.start})
    await this.cache.load(target.native,controller.signal);check();await this.cache.load(plan.asset,controller.signal);check();if(body.url!==target.native.url){await this.cache.load(body,controller.signal);check()}
    if(options.automatic&&plan.start<this.position+.25)continue
    if(options.automatic)this.automaticPrepared={source:active,targetId:trackId,result}
    this.log('next_preparation_ready',{trackId,from:active.track.id,candidateId:plan.id,automatic:!!options.automatic,plannedStart:plan.start});this.update();return
   }
   throw new Error('下载期间错过了预定接点，正在重新选择下一首。')
  }catch(error){if(token===this.prepareSequence){this.preparedPins.clear();this.automaticPrepared=null;this.protected()}throw error}
  finally{if(token===this.prepareSequence)this.prepareLoad=null}
 }
 private checkSegments(){
  const decks=[this.active,this.pending?.deck].filter(Boolean) as Deck[]
  if(!decks.some(d=>d.stream))return
  for(const deck of decks)deck.stream?.pump();this.protected()
  const waiting=decks.find(d=>d.stream&&d.stream.deadline<=this.ctx.currentTime+.5&&!(d===this.active&&this.pending&&d.stream.deadline>=this.pending.end))
  if(waiting){
   if(!this.buffering){this.buffering=true;this.status='正在缓冲整曲音频，播放时钟已暂停…';this.log('segment_buffering',{track:waiting.track.id,sourcePosition:this.position,coveredUntil:waiting.stream!.coveredSourceEnd})
    const token=this.starting,promise=this.ctx.suspend();this.bufferSuspend=promise;void promise.then(()=>{if(token===this.starting){this.bufferSuspend=null;this.checkSegments();this.update()}})
   }
   if(waiting.stream!.error)this.status='整曲音频准备失败：'+waiting.stream!.error+'；暂停后继续可重试'
   if(waiting.stream!.late&&!this.bufferSuspend){const active=this.active,position=Math.min(this.position,active?.stream?.coveredSourceEnd??this.position),pause=this.paused;if(active){this.log('segment_deadline_missed',{track:active.track.id,resumeSourceSec:position,reason:'后台调度晚于边界；撤销未完成转场并从已覆盖位置恢复'});void this.start(active.track.id,position,pause).catch(()=>this.update())}}
   return
  }
  if(this.buffering&&!this.bufferSuspend&&!this.bufferResume){
   this.bufferResume=true;const token=this.starting
   void (async()=>{try{if(!this.paused)await this.ctx.resume();if(token!==this.starting)return;if(this.paused)await this.ctx.suspend();this.buffering=false;this.status=this.paused?'已暂停，交接时钟同时暂停':'整曲音频已就绪，继续播放';this.log('segment_buffering_complete',{sourcePosition:this.position,paused:this.paused})}finally{if(token===this.starting){this.bufferResume=false;this.update()}}})()
  }
 }
 private sync(){
  const p=this.pending;if(!p)return;const now=this.ctx.currentTime
  if(now>=p.start-.15&&!this.gate.locked){this.gate.locked=true;this.log('plan_locked',{requestId:p.requestId,planId:p.id,reason:'距混入点不足 150 ms，后续普通请求延后处理'})}
  if(now>=p.end){
   const old=this.active;this.active=p.deck;this.active.at=p.end;this.active.offset=p.plan.window.end;this.pending=null;this.cancelPreparation();this.gate.locked=false;this.autoTried=false
   if(old)this.retire(old,false)
   this.log('handoff_state_commit',{requestId:p.requestId,planId:p.id,to:this.active.track.id,bodySourceOffset:this.active.offset,scheduledContextSec:p.end})
   this.outcome(p.requestId,'completed','计划交接时点已到，B 正文接管；实际音频处理块观察另见 audio_observation',{planId:p.id})
   this.currentRequestId=null;this.status='交接完成，正文恢复原速';this.protected()
   const next=this.gate.deferred,requestId=this.deferredRequestId;this.gate.deferred=null;this.deferredRequestId=null
   if(next&&requestId){const remaining=this.deferredDeadline-now;if(remaining>0)void this.request(next,remaining,{resumeId:requestId});else{this.status='等待上限已到，保留当前播放；请重新选择';this.outcome(requestId,'expired','等待当前交接结束期间已超过原始等待上限',{deadline:this.deferredDeadline})}}
   else void this.prewarm()
  }
 }
 private tick(){if(this.dead)return;this.checkSegments();this.sync();if(this.comparisonEnd!==null&&this.ctx.currentTime>=this.comparisonEnd){this.log('comparison_finished',{comparisonId:this.comparisonId,reason:'交接后8秒试听结束'});this.stop();this.status='本次对照试听结束';this.update();return}if(this.active&&this.ctx.state==='running'&&!this.paused&&!this.pending&&!this.busy){const left=this.active.track.duration-this.position;if(left<20&&!this.autoTried&&!this.comparisonMode&&this.options.autoNext!==false){this.autoTried=true;void this.request({kind:'next'},18,{origin:'source_end_auto'})}if(left<=.01){this.stop();this.status='本段试听已播完';this.log('source_end')}}this.update()}
 cancel(){this.sync();if(this.gate.locked){this.log('cancel_denied',{requestId:this.currentRequestId,planId:this.pending?.id,reason:'交接已锁定，取消不会打断当前声音；仍可停止'});this.status='交接已锁定；可停止播放，普通请求将在完成后处理';this.update();return false}this.outcome(this.currentRequestId,'cancelled','用户取消待执行请求');this.outcome(this.deferredRequestId,'cancelled','用户取消等待中的请求');if(!this.active)this.starting++;this.startLoad?.abort();this.requestLoad?.abort();this.startPins.clear();this.requestPins.clear();this.gate.reset();this.busy=false;this.cancelScheduled();this.currentRequestId=null;this.deferredRequestId=null;this.protected();this.log('request_cancelled');this.status='已取消待执行转场';this.update();return true}
 private cancelScheduled(){const p=this.pending;if(!p)return;this.monitor.port.postMessage({kind:'cancel',planId:p.id});this.retire(p.deck,false);if(this.active){this.hold(this.active.gain.gain,.76);this.hold(this.active.wet.gain,0);this.hold(this.active.dry.gain,1);if(p.plan.v30Eq)for(const band of ['low','mid','high'] as const)this.hold(this.active[band].gain,0)}this.log('plan_cancelled',{requestId:p.requestId,planId:p.id,reason:'撤销尚未执行的自动化并恢复 A 原始增益'});this.pending=null;this.protected()}
 async request(intent:Intent,budget=18,options:{resumeId?:string;origin?:string;automatic?:boolean}={}){
  this.sync()
  if(options.automatic&&this.active)budget=Math.max(0,this.active.track.duration-this.position-.1)
  const requestId=options.resumeId||`${this.sessionId}:request-${++this.requestSequence}`
  if(!options.resumeId)this.log('request_received',{requestId,intent,origin:options.origin||'user',sourceTrackId:this.active?.track.id||null,sourcePosition:this.position,budgetSec:budget,deadlineContextSec:this.ctx.currentTime+budget,policyVersion:this.options.policyVersion||DECISION_POLICY.version})
  else this.log('request_resumed',{requestId,remainingBudgetSec:budget,sourceTrackId:this.active?.track.id,sourcePosition:this.position})
  if(!this.active||this.paused){this.status='请先播放歌曲';this.outcome(requestId,'rejected',this.paused?'当前处于暂停状态':'当前没有播放曲目');this.update();return}
  const token=this.gate.replace(intent)
  this.log('intent',{requestId,intent,revision:token,sourcePosition:this.position,budget})
  if(token===null){
   this.outcome(this.deferredRequestId,'superseded','被交接期间较新的请求替代',{replacementRequestId:requestId})
   this.deferredRequestId=requestId;this.deferredDeadline=this.ctx.currentTime+budget
   this.log('request_deferred',{requestId,waitingForPlanId:this.pending?.id,deadlineContextSec:this.deferredDeadline,reason:'当前交接已锁定，保留最新意图，完成后按剩余预算重新规划'})
   this.status='当前交接已锁定，将在完成后处理最新请求';this.update();return
  }
  this.outcome(this.currentRequestId,'superseded','被新混音请求替代',{replacementRequestId:requestId})
  this.requestLoad?.abort();const controller=new AbortController();this.requestLoad=controller;this.requestPins.clear();this.cancelScheduled();this.currentRequestId=requestId;this.automaticRequestId=options.automatic?requestId:null
  const source=this.active.track,requestedAt=this.ctx.currentTime
  this.busy=true;this.status='正在选择可用交接窗口…';this.update()
  try{
   const search=(remaining:number,requireReady=true)=>{
    if(!options.automatic)return (this.options.planner||planNext)(source,this.tracks,this.position,intent,this.cache.ready,remaining,requireReady)
    const prepared=this.automaticPrepared,p=prepared?.result.best
    if(prepared?.source===this.active&&prepared.targetId===intent.targetId&&p&&p.start>=this.position+.25&&
      (!requireReady||[p.asset.url,this.tracks.find(t=>t.id===p.to)!.native.url,nativeSegment(this.tracks.find(t=>t.id===p.to)!,p.window.end).asset.url].every(url=>this.cache.ready.has(url))))return {...prepared.result,best:{...p,prepared:true},candidates:prepared.result.candidates.map(c=>({...c,prepared:this.cache.ready.has(c.asset.url)&&this.cache.ready.has(this.tracks.find(t=>t.id===c.to)!.native.url)}))}
    return planAutomatic(this.options.planner||planNext,source,this.tracks,this.position,intent,this.cache.ready,requireReady)
   }
   let result=search(budget)
   this.auditSearch(requestId,'ready_assets',result,this.position,budget)
   const readyBody=result.best?nativeSegment(this.tracks.find(t=>t.id===result.best!.to)!,result.best.window.end).asset:null
   if(!result.best||!this.cache.ready.has(readyBody!.url)){
    const preview=search(budget,false)
    this.lastSearch=preview;this.auditSearch(requestId,'preparation_preview',preview,this.position,budget)
    if(!preview.best)throw new Error(this.options.noPlanMessage||'等待范围内没有符合目标的窗口。可以改用较长等待或选择其他歌曲。')
    const b=this.tracks.find(t=>t.id===preview.best!.to)!
    this.log('preparation_started',{requestId,candidateId:preview.best.id,provisionalDecision:preview.best.decision,assets:[b.native,preview.best.asset],reason:'暂定候选，素材准备后必须按剩余预算重新选点，不承诺执行此窗口'})
    const body=nativeSegment(b,preview.best.window.end).asset
    this.requestPins=new Set([b.native.url,preview.best.asset.url,body.url]);this.protected()
    await this.cache.load(b.native,controller.signal);if(!this.gate.isCurrent(token))return
    await this.cache.load(preview.best.asset,controller.signal);if(!this.gate.isCurrent(token))return
    if(body.url!==b.native.url){await this.cache.load(body,controller.signal);if(!this.gate.isCurrent(token))return}
    const remaining=budget-(this.ctx.currentTime-requestedAt)
    this.log('preparation_completed',{requestId,elapsedSec:this.ctx.currentTime-requestedAt,remainingBudgetSec:remaining})
    result=search(remaining)
    this.auditSearch(requestId,'after_preparation',result,this.position,remaining)
   }
   if(!this.gate.isCurrent(token)||this.active?.track.id!==source.id)return
   this.lastSearch=result
   if(!result.best)throw new Error('素材已准备，但原来的交接窗口已错过。当前歌曲继续播放，请再次选择。')
   this.schedule(result.best,requestedAt,intent,requestId,result)
   if(this.pending)this.pending.automatic=!!options.automatic
  }catch(e){if(this.gate.isCurrent(token)){this.status=(e as Error).message;this.log('request_failed',{requestId,message:this.status,intent});this.outcome(requestId,'failed',this.status)}}
  finally{if(this.automaticRequestId===requestId)this.automaticRequestId=null;if(this.gate.isCurrent(token)){this.requestLoad=null;this.requestPins.clear();this.busy=false;this.protected();this.update()}}
 }
 private schedule(plan:Plan,requestedAt:number,intent:Intent,requestId:string,search:ReturnType<typeof planNext>){const a=this.active!;const b=this.tracks.find(t=>t.id===plan.to)!;const start=a.at+(plan.start-a.offset),end=start+plan.duration;const restore=end-Math.min(plan.duration,120/a.track.bpm);if(start<this.ctx.currentTime+.2)throw new Error('距离进歌点太近，已保留当前播放');const native=this.cache.buffers.get(nativeSegment(b,plan.window.end).asset.url),clip=this.cache.buffers.get(plan.asset.url);if(!native||!clip)throw new Error('正文片段尚未就绪，当前歌曲继续播放');const deck=this.graph(b,end,plan.window.end);this.source(deck,clip,start,0,end);this.nativeSource(deck,native,end,plan.window.end,true)
  const id=`${this.gate.revision}-${plan.id}`,runnerUp=search.candidates.find(c=>c.id!==plan.id)
  if(plan.automation){scheduleAutomation(a,deck,start,plan.automation);this.log('phrase_automation',{requestId,planId:id,candidatePlanId:plan.id,sourceStart:plan.start,contextStart:start,phrase:plan.phrase,automation:plan.automation})}else{
  a.low.gain.setValueAtTime(-9,start);a.high.gain.setValueAtTime(-1.4,start);a.mid.gain.setValueAtTime(0,start);a.wet.gain.setValueAtTime(0,start);a.wet.gain.linearRampToValueAtTime(1,start+.02);a.dry.gain.setValueAtTime(1,start);a.dry.gain.linearRampToValueAtTime(0,start+.02);a.gain.gain.setValueAtTime(.76,start);a.gain.gain.linearRampToValueAtTime(0,end)
  deck.low.gain.value=-7;deck.high.gain.value=1.2;deck.mid.gain.value=plan.midDuck?this.comparisonMidDb:0;deck.wet.gain.setValueAtTime(1,start);deck.wet.gain.setValueAtTime(1,restore);deck.wet.gain.linearRampToValueAtTime(0,end);deck.dry.gain.setValueAtTime(0,start);deck.dry.gain.setValueAtTime(0,restore);deck.dry.gain.linearRampToValueAtTime(1,end);deck.gain.gain.setValueAtTime(0,start);deck.gain.gain.linearRampToValueAtTime(.76,end)
  if(plan.v30Eq){scheduleV30Eq(a,deck,start,plan.v30Eq);this.log('v30_eq_automation',{requestId,planId:id,contextStart:start,eq:plan.v30Eq,gainAndWetDry:'unchanged V3 full-overlap linear'})}
  }
  this.pending={plan,deck,start,end,id,committed:false,requestId};this.lastPlan=plan;const events=[{name:'B 开始混入',time:start},...(plan.phrase?[{name:'A 尾音保护结束 / 开始退让',time:start+plan.phrase.fadeStart-plan.start}]:[]),{name:'B EQ 开始恢复',time:restore},{name:'A 退出 / B 正文接管',time:end}].map(e=>({planId:id,requestId,name:e.name,frame:Math.round(e.time*this.ctx.sampleRate)}));this.monitor.port.postMessage({kind:'arm',events});this.log('plan_scheduled',{trace:buildDecisionTrace(a.track,b,plan,this.comparisonMidDb),actualBMidDb:plan.automation||plan.v30Eq?null:plan.midDuck?this.comparisonMidDb:0,automation:plan.automation||null,phrase:plan.phrase||null,requestId,planId:id,selection:{candidateCount:search.candidates.length,chosenRank:Math.max(0,search.candidates.findIndex(c=>c.id===plan.id))+1,tieBreak:plan.decision?.score.tieBreak||DECISION_POLICY.ranking,runnerUp:runnerUp?{id:runnerUp.id,score:runnerUp.score,gap:plan.score-runnerUp.score}:null,reason:plan.v30Tune?plan.v30Tune.reason:plan.phrase?'先通过乐句、人声间距和拍点约束，再依等待与间距选择；EQ 不改变选点':this.options.policyVersion?.startsWith('protected')?'先通过全部保护约束，再取最早完成的核验点':this.comparisonMode?'受控回放已经选定的计划；不在播放时重新排名，完整候选见 comparison_analysis':search.candidates.length===1?'唯一满足本次约束的已就绪候选':'按规则分降序选择；同分按完成时间及 ID 排序',strategyReason:plan.decision?.strategy.selectionReason},intent,requestedAt,start,end,restore,plan,events,eqImplementation:plan.v30Eq?'V3 original full-overlap gains and wet/dry; bounded source-dependent EQ coefficient curves only':plan.automation?'WebAudio Biquad; explicit source-energy automation, linear ramps and source-bound curve evidence; 4ms head/body edges':'WebAudio Biquad, V3 gains/frequencies; 20ms outgoing EQ enable smoothing; 4ms head/body edge fades',limiter:'5ms lookahead browser protection, not original FFmpeg alimiter',sourceHashes:{a:a.track.native.sha256,b:b.native.sha256,entry:plan.asset.sha256}});this.status='已安排转场';this.protected();this.update()}

 async playComparison(plan:Plan,position:number,experiment:ComparisonRun){
  if(![-5,-8].includes(experiment.midDb)||!Number.isFinite(position)||!Number.isFinite(plan.start)||!Number.isFinite(plan.end)||plan.start<position+.25||Math.abs(plan.end-plan.start-plan.duration)>1/44100||Math.abs(plan.asset.duration-plan.duration)>1/44100)throw new Error('对照计划的时刻或处理参数不合法')
  const a=this.tracks.find(t=>t.id===plan.from),b=this.tracks.find(t=>t.id===plan.to)
  if(!a||!b||plan.end>=a.duration||plan.window.end+8>b.duration)throw new Error('对照素材范围不完整')
  const token=++this.starting;this.stop(false);this.comparisonMode=true;this.comparisonMidDb=experiment.midDb;this.comparisonId=String(experiment.comparisonId||experiment.experimentId+':'+experiment.arm);this.busy=true;this.status='正在准备本次固定对照的素材…';this.update()
  const requestId=`${this.sessionId}:comparison-${++this.requestSequence}`;this.currentRequestId=requestId
  this.log('request_received',{requestId,intent:{kind:'next',targetId:b.id},origin:'controlled_comparison',sourceTrackId:a.id,sourcePosition:position,budgetSec:experiment.horizonSec||18,experiment,note:'预先规划的受控源时间触发点；不是用户在该时刻实际点击'})
  try{
   await this.ctx.resume();if(token!==this.starting||this.dead)return
   this.cache.protected=new Set([a.native.url,b.native.url,plan.asset.url])
   const loadStart=performance.now();const previouslyReady=this.cache.ready;await Promise.all([a.native,b.native,plan.asset].map(asset=>this.cache.load(asset)));if(token!==this.starting||this.dead)return;this.log('audio_preparation',{elapsedMs:performance.now()-loadStart,reusedAssets:[a.native,b.native,plan.asset].filter(asset=>previouslyReady.has(asset.url)).map(asset=>asset.url),assetCount:3,parallel:true})
   const at=this.ctx.currentTime+.08,offset=Math.max(0,(experiment.skipWaiting===true?plan.start:position)-4)
   this.active=this.graph(a,at,offset);this.nativeSource(this.active,this.cache.buffers.get(a.native.url)!,at,offset);this.active.gain.gain.setValueAtTime(0,at);this.active.gain.gain.linearRampToValueAtTime(.76,at+.02)
   this.paused=false;this.log('track_start',{track:a.id,sourceOffset:offset,scheduledAt:at,assetSha256:a.native.sha256})
   this.log('comparison_started',{requestId,experiment,plan,sourcePlaybackStart:offset,virtualTriggerSourceSec:position,virtualTriggerContextSec:position>=offset?at+position-offset:null,skippedWaitingSec:Math.max(0,offset-position),cacheProtocol:'A、B和进入素材全部就绪后开始；关闭自动接歌与背景预加载'})
   this.schedule(plan,at+position-offset,{kind:'next',targetId:b.id},requestId,{best:plan,candidates:[plan],rejected:[],exclusions:[]})
   this.comparisonEnd=at+(plan.end-offset)+8;this.protected()
  }catch(e){if(token===this.starting){this.outcome(requestId,'failed',(e as Error).message);this.stop();this.status=(e as Error).message}throw e}
  finally{if(token===this.starting){this.busy=false;this.update()}}
 }
 private async prewarm(){if(this.comparisonMode||this.options.prewarm===false)return;const a=this.active;if(!a)return;const revision=this.starting;const intents:Intent[]=[{kind:'next'},{kind:'style',style:a.track.style==='Trap'?'Grime':'Trap'}];for(const intent of intents){if(this.pending||this.busy||this.active!==a||revision!==this.starting)return;const p=planNext(a.track,this.tracks,Math.max(this.position,(a.track.bars[0]||0)+1),intent,this.cache.ready,30,false).best;if(!p)continue;try{const b=this.tracks.find(t=>t.id===p.to)!;await this.cache.load(b.native);if(this.active!==a||this.pending)return;await this.cache.load(p.asset)}catch(e){this.log('prewarm_failed',{message:(e as Error).message})}}this.update()}
 export(){return {schema:'harbeat.v3_live_session.v2',sessionId:this.sessionId,...(this.options.release?{release:this.options.release}:{}),policy:this.options.policyVersion?{version:this.options.policyVersion,ranking:this.options.policyVersion==='vocal-overlap-v1'?'Same V3.1 entry asset/rate/duration; replace vocal term with aligned gain-weighted activity; unchanged other score terms and dynamic EQ':this.options.policyVersion.startsWith('v30-original-dynamic')?'Original V3 ranking and full overlap; source-dependent bounded EQ only':this.options.policyVersion.startsWith('v30')?'Original V3 ranking; optional eligible adjacent-bar correction; independent bounded EQ':this.options.policyVersion.startsWith('phrase')?'Hard phrase/timing constraints; wait plus vocal-gap cost, then stable ID; EQ does not rerank':"Hard constraints, earliest verified exit then rate deviation then ID"}:DECISION_POLICY,retention:'完整事件自动保存在同源同浏览器 IndexedDB；仍可导出，不上传服务器。清理站点数据会删除本地记录。',catalog:this.tracks.map(t=>({...t})),sampleRate:this.ctx.sampleRate,baseLatency:this.ctx.baseLatency,outputLatency:this.ctx.outputLatency,logs:this.logs,limitations:['Audio observations locate render quanta, not physical source onset/speaker output','Single-song tempo assets were prepared ahead; selection/EQ/fade/mixing run live','Browser DSP is not bit-identical to FFmpeg V3','Energy uses common dBFS RMS, not validated perceived energy; all structural candidates need listening confirmation']}}
 dispose(){this.dead=true;this.stop();window.removeEventListener?.('pagehide',this.flushSession);this.flushSession();clearInterval(this.timer);this.cache.dispose();void this.ctx.close()}
}
