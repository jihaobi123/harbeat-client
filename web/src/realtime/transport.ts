import {SessionWriter,saveSession} from './sessionStore'
import {DECISION_POLICY} from './decision'
import {AudioCache} from './cache'
import {planNext,RequestGate,Track,Intent,Plan} from './planner'
export type Log=Record<string,any>
export type ComparisonRun={experimentId:string;arm:'baseline'|'variant';midDb:-5|-8;[key:string]:unknown}
type Deck={track:Track;sources:AudioBufferSourceNode[];nodes:AudioNode[];gain:GainNode;dry:GainNode;wet:GainNode;low:BiquadFilterNode;high:BiquadFilterNode;mid:BiquadFilterNode;at:number;offset:number;headEnd?:number;bodyOffset?:number;rate?:number}
type Pending={plan:Plan;deck:Deck;start:number;end:number;id:string;committed:boolean;requestId:string}
export class LiveTransport{
 private comparisonId:string|null=null;private comparisonMode=false;private comparisonEnd:number|null=null;private comparisonMidDb=-5;
 persistenceStatus='会话尚未保存';private recorder:SessionWriter|null=null;private flushSession=()=>{void this.recorder?.flush()};
 ctx:AudioContext;cache:AudioCache;gate=new RequestGate();logs:Log[]=[];active:Deck|null=null;pending:Pending|null=null;status='选择歌曲后开始播放';lastPlan:Plan|null=null;lastSearch:any=null;paused=false;busy=false;private monitor!:AudioWorkletNode;private volume:GainNode;private timer:number;private starting=0;private autoTried=false;private base:URL;private dead=false;private deferredDeadline=0;private requestSequence=0;private currentRequestId:string|null=null;private deferredRequestId:string|null=null;private terminalRequests=new Set<string>();readonly sessionId=`live-${Date.now()}-${Math.random().toString(36).slice(2,10)}`
 constructor(public tracks:Track[],private update:()=>void,base:URL){this.base=base;this.ctx=new AudioContext({sampleRate:44100,latencyHint:'interactive'});this.volume=this.ctx.createGain();this.volume.gain.value=.85;this.volume.connect(this.ctx.destination);this.cache=new AudioCache(this.ctx,base,s=>{if(this.busy||!this.active){this.status=s;this.update()}});this.timer=window.setInterval(()=>this.tick(),80);if(typeof indexedDB!=='undefined'){this.recorder=new SessionWriter(()=>this.export(),saveSession,status=>{this.persistenceStatus=status;if(!this.dead)this.update()});window.addEventListener('pagehide',this.flushSession)}this.ctx.onstatechange=()=>{this.log('context_state',{state:this.ctx.state});this.update()}}
 async initialize(){await this.ctx.audioWorklet.addModule(new URL('v3-clock.js',this.base));this.monitor=new AudioWorkletNode(this.ctx,'v3-clock',{outputChannelCount:[2]});this.monitor.connect(this.volume);this.monitor.port.onmessage=({data})=>{this.log('audio_observation',{...data,plannedContextSec:data.frame/this.ctx.sampleRate,observedContextSec:data.observedFrame/this.ctx.sampleRate,observationDeltaMs:(data.observedFrame-data.frame)/this.ctx.sampleRate*1000,messageReceivedContextSec:this.ctx.currentTime,basis:'Audio-thread render quantum observation; not measured source onset, device output or Bluetooth latency'});this.sync();this.update()}}
 log(kind:string,data:Log={}){this.logs.push(JSON.parse(JSON.stringify({kind,sessionId:this.sessionId,sequence:this.logs.length+1,wallTime:new Date().toISOString(),contextSec:this.ctx.currentTime,...data})));if(this.recorder){if(['request_received','plan_scheduled','audio_observation','request_outcome','track_stop'].includes(kind))void this.recorder.flush();else this.recorder.queue()}}
 private outcome(requestId:string|null,outcome:string,reason:string,extra:Log={}){if(!requestId||this.terminalRequests.has(requestId))return;this.terminalRequests.add(requestId);this.log('request_outcome',{requestId,outcome,reason,...extra})}
 private auditSearch(requestId:string,phase:string,result:ReturnType<typeof planNext>,position:number,budget:number){
  const ranked=result.candidates.map((p,rank)=>({rank:rank+1,id:p.id,to:p.to,windowId:p.window.id,start:p.start,end:p.end,score:p.score,prepared:p.prepared,scoreComponents:p.decision?.score.components,reason:p.reason,localEvidence:p.evidence}))
  this.log('decision_search',{requestId,phase,sourcePosition:position,remainingBudgetSec:budget,result:{candidateCount:ranked.length,selectedId:result.best?.id||null,candidates:ranked,exclusions:result.exclusions,rejected:result.rejected},policyVersion:DECISION_POLICY.version})
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
 private source(d:Deck,buffer:AudioBuffer,at:number,offset:number,until?:number,edge=false){const s=this.ctx.createBufferSource(),g=this.ctx.createGain();s.buffer=buffer;s.connect(g);g.connect(d.nodes[0]);s.start(at,offset);if(until){g.gain.setValueAtTime(1,Math.max(at,until-.004));g.gain.linearRampToValueAtTime(0,until);s.stop(until)}else if(edge){g.gain.setValueAtTime(0,at);g.gain.linearRampToValueAtTime(1,at+.004)}d.sources.push(s);d.nodes.push(g)}
 private retire(d:Deck,fade=true){const now=this.ctx.currentTime;if(fade)this.hold(d.gain.gain,0);for(const s of d.sources){try{s.stop(now+(fade?.025:0))}catch{}}setTimeout(()=>d.nodes.forEach(n=>{try{n.disconnect()}catch{}}),80)}
 private protected(){this.cache.protected=new Set([this.active?.track.native.url,this.pending?.deck.track.native.url,this.pending?.plan.asset.url].filter(Boolean) as string[])}
 async start(id:string,offset=0){const token=++this.starting;this.stop(false);this.busy=true;this.status='正在准备原曲…';this.update();await this.ctx.resume();const t=this.tracks.find(t=>t.id===id);if(!t)throw new Error('歌曲不存在');try{this.cache.protected=new Set([t.native.url]);const buffer=await this.cache.load(t.native);if(token!==this.starting||this.dead)return;const at=this.ctx.currentTime+.08;this.active=this.graph(t,at,Math.max(0,Math.min(t.duration-1,offset)));this.source(this.active,buffer,at,this.active.offset);this.active.gain.gain.setValueAtTime(0,at);this.active.gain.gain.linearRampToValueAtTime(.76,at+.02);this.paused=false;this.status='正在播放';this.autoTried=false;this.log('track_start',{track:t.id,sourceOffset:this.active.offset,scheduledAt:at,assetSha256:t.native.sha256});this.protected();}finally{if(token===this.starting){this.busy=false;this.update();if(this.active)void this.prewarm()}}}
 stop(invalidate=true){this.comparisonMode=false;this.comparisonEnd=null;this.comparisonMidDb=-5;this.outcome(this.currentRequestId,'stopped','播放停止或重新开始，撤销尚未完成的混音');this.outcome(this.deferredRequestId,'stopped','播放停止，清除等待中的请求');this.currentRequestId=null;this.deferredRequestId=null;if(invalidate)this.starting++;this.gate.reset();if(this.pending)this.retire(this.pending.deck);if(this.active)this.retire(this.active);this.pending=null;this.active=null;this.busy=false;this.paused=false;this.autoTried=false;this.monitor?.port.postMessage({kind:'clear'});this.cache.protected.clear();this.status='已停止';this.log('stop');this.update()}
 async togglePause(){if(!this.active)return;if(this.paused){await this.ctx.resume();this.paused=false;this.status='继续播放'}else{await this.ctx.suspend();this.paused=true;this.status='已暂停，交接时钟同时暂停'}this.log('pause',{paused:this.paused});this.update()}
 async seek(position:number){if(!this.active)return;const id=this.active.track.id;this.log('seek',{position});await this.start(id,position)}
 private sync(){
  const p=this.pending;if(!p)return;const now=this.ctx.currentTime
  if(now>=p.start-.15&&!this.gate.locked){this.gate.locked=true;this.log('plan_locked',{requestId:p.requestId,planId:p.id,reason:'距混入点不足 150 ms，后续普通请求延后处理'})}
  if(now>=p.end){
   const old=this.active;this.active=p.deck;this.active.at=p.end;this.active.offset=p.plan.window.end;this.pending=null;this.gate.locked=false;this.autoTried=false
   if(old)this.retire(old,false)
   this.log('handoff_state_commit',{requestId:p.requestId,planId:p.id,to:this.active.track.id,bodySourceOffset:this.active.offset,scheduledContextSec:p.end})
   this.outcome(p.requestId,'completed','计划交接时点已到，B 正文接管；实际音频处理块观察另见 audio_observation',{planId:p.id})
   this.currentRequestId=null;this.status='交接完成，正文恢复原速';this.protected()
   const next=this.gate.deferred,requestId=this.deferredRequestId;this.gate.deferred=null;this.deferredRequestId=null
   if(next&&requestId){const remaining=this.deferredDeadline-now;if(remaining>0)void this.request(next,remaining,{resumeId:requestId});else{this.status='等待上限已到，保留当前播放；请重新选择';this.outcome(requestId,'expired','等待当前交接结束期间已超过原始等待上限',{deadline:this.deferredDeadline})}}
   else void this.prewarm()
  }
 }
 private tick(){if(this.dead)return;this.sync();if(this.comparisonEnd!==null&&this.ctx.currentTime>=this.comparisonEnd){this.log('comparison_finished',{comparisonId:this.comparisonId,reason:'交接后8秒试听结束'});this.stop();this.status='本次对照试听结束';this.update();return}if(this.active&&this.ctx.state==='running'&&!this.paused&&!this.pending&&!this.busy){const left=this.active.track.duration-this.position;if(left<20&&!this.autoTried&&!this.comparisonMode){this.autoTried=true;void this.request({kind:'next'},18,{origin:'source_end_auto'})}if(left<=.01){this.stop();this.status='本段试听已播完';this.log('source_end')}}this.update()}
 cancel(){this.sync();if(this.gate.locked){this.log('cancel_denied',{requestId:this.currentRequestId,planId:this.pending?.id,reason:'交接已锁定，取消不会打断当前声音；仍可停止'});this.status='交接已锁定；可停止播放，普通请求将在完成后处理';this.update();return false}this.outcome(this.currentRequestId,'cancelled','用户取消待执行请求');this.outcome(this.deferredRequestId,'cancelled','用户取消等待中的请求');this.starting++;this.gate.reset();this.busy=false;this.cancelScheduled();this.currentRequestId=null;this.deferredRequestId=null;this.protected();this.log('request_cancelled');this.status='已取消待执行转场';this.update();return true}
 private cancelScheduled(){const p=this.pending;if(!p)return;this.monitor.port.postMessage({kind:'cancel',planId:p.id});this.retire(p.deck,false);if(this.active){this.hold(this.active.gain.gain,.76);this.hold(this.active.wet.gain,0);this.hold(this.active.dry.gain,1)}this.log('plan_cancelled',{requestId:p.requestId,planId:p.id,reason:'撤销尚未执行的自动化并恢复 A 原始增益'});this.pending=null;this.protected()}
 async request(intent:Intent,budget=18,options:{resumeId?:string;origin?:string}={}){
  this.sync()
  const requestId=options.resumeId||`${this.sessionId}:request-${++this.requestSequence}`
  if(!options.resumeId)this.log('request_received',{requestId,intent,origin:options.origin||'user',sourceTrackId:this.active?.track.id||null,sourcePosition:this.position,budgetSec:budget,deadlineContextSec:this.ctx.currentTime+budget,policyVersion:DECISION_POLICY.version})
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
  this.cancelScheduled();this.currentRequestId=requestId
  const source=this.active.track,requestedAt=this.ctx.currentTime
  this.busy=true;this.status='正在选择可用交接窗口…';this.update()
  try{
   let result=planNext(source,this.tracks,this.position,intent,this.cache.ready,budget)
   this.auditSearch(requestId,'ready_assets',result,this.position,budget)
   if(!result.best){
    const preview=planNext(source,this.tracks,this.position,intent,this.cache.ready,budget,false)
    this.lastSearch=preview;this.auditSearch(requestId,'preparation_preview',preview,this.position,budget)
    if(!preview.best)throw new Error('等待范围内没有符合目标的窗口。可以改用较长等待或选择其他歌曲。')
    const b=this.tracks.find(t=>t.id===preview.best!.to)!
    this.log('preparation_started',{requestId,candidateId:preview.best.id,provisionalDecision:preview.best.decision,assets:[b.native,preview.best.asset],reason:'暂定候选，素材准备后必须按剩余预算重新选点，不承诺执行此窗口'})
    this.cache.protected.add(b.native.url);this.cache.protected.add(preview.best.asset.url)
    await this.cache.load(b.native);if(!this.gate.isCurrent(token))return
    await this.cache.load(preview.best.asset);if(!this.gate.isCurrent(token))return
    const remaining=budget-(this.ctx.currentTime-requestedAt)
    this.log('preparation_completed',{requestId,elapsedSec:this.ctx.currentTime-requestedAt,remainingBudgetSec:remaining})
    result=planNext(source,this.tracks,this.position,intent,this.cache.ready,remaining)
    this.auditSearch(requestId,'after_preparation',result,this.position,remaining)
   }
   if(!this.gate.isCurrent(token)||this.active?.track.id!==source.id)return
   this.lastSearch=result
   if(!result.best)throw new Error('素材已准备，但原来的交接窗口已错过。当前歌曲继续播放，请再次选择。')
   this.schedule(result.best,requestedAt,intent,requestId,result)
  }catch(e){if(this.gate.isCurrent(token)){this.status=(e as Error).message;this.log('request_failed',{requestId,message:this.status,intent});this.outcome(requestId,'failed',this.status)}}
  finally{if(this.gate.isCurrent(token)){this.busy=false;this.protected();this.update()}}
 }
 private schedule(plan:Plan,requestedAt:number,intent:Intent,requestId:string,search:ReturnType<typeof planNext>){const a=this.active!;const b=this.tracks.find(t=>t.id===plan.to)!;const start=a.at+(plan.start-a.offset),end=start+plan.duration;const restore=end-Math.min(plan.duration,120/a.track.bpm);if(start<this.ctx.currentTime+.2)throw new Error('距离进歌点太近，已保留当前播放');const native=this.cache.buffers.get(b.native.url)!,clip=this.cache.buffers.get(plan.asset.url)!;const deck=this.graph(b,end,plan.window.end);this.source(deck,clip,start,0,end);this.source(deck,native,end,plan.window.end,undefined,true)
  a.low.gain.setValueAtTime(-9,start);a.high.gain.setValueAtTime(-1.4,start);a.mid.gain.setValueAtTime(0,start);a.wet.gain.setValueAtTime(0,start);a.wet.gain.linearRampToValueAtTime(1,start+.02);a.dry.gain.setValueAtTime(1,start);a.dry.gain.linearRampToValueAtTime(0,start+.02);a.gain.gain.setValueAtTime(.76,start);a.gain.gain.linearRampToValueAtTime(0,end)
  deck.low.gain.value=-7;deck.high.gain.value=1.2;deck.mid.gain.value=plan.midDuck?this.comparisonMidDb:0;deck.wet.gain.setValueAtTime(1,start);deck.wet.gain.setValueAtTime(1,restore);deck.wet.gain.linearRampToValueAtTime(0,end);deck.dry.gain.setValueAtTime(0,start);deck.dry.gain.setValueAtTime(0,restore);deck.dry.gain.linearRampToValueAtTime(1,end);deck.gain.gain.setValueAtTime(0,start);deck.gain.gain.linearRampToValueAtTime(.76,end)
  const id=`${this.gate.revision}-${plan.id}`;this.pending={plan,deck,start,end,id,committed:false,requestId};this.lastPlan=plan;const events=[{name:'B 开始混入',time:start},{name:'B EQ 开始恢复',time:restore},{name:'A 退出 / B 正文接管',time:end}].map(e=>({planId:id,requestId,name:e.name,frame:Math.round(e.time*this.ctx.sampleRate)}));this.monitor.port.postMessage({kind:'arm',events});this.log('plan_scheduled',{actualBMidDb:plan.midDuck?this.comparisonMidDb:0,requestId,planId:id,selection:{candidateCount:search.candidates.length,chosenRank:1,tieBreak:DECISION_POLICY.ranking,runnerUp:search.candidates[1]?{id:search.candidates[1].id,score:search.candidates[1].score,gap:plan.score-search.candidates[1].score}:null,reason:this.comparisonMode?'受控回放已经选定的计划；不在播放时重新排名，完整候选见 comparison_analysis':search.candidates.length===1?'唯一满足本次约束的已就绪候选':'按规则分降序选择；同分按完成时间及 ID 排序',strategyReason:plan.decision?.strategy.selectionReason},intent,requestedAt,start,end,restore,plan,events,eqImplementation:'WebAudio Biquad, V3 gains/frequencies; 20ms outgoing EQ enable smoothing; 4ms head/body edge fades',limiter:'5ms lookahead browser protection, not original FFmpeg alimiter',sourceHashes:{a:a.track.native.sha256,b:b.native.sha256,entry:plan.asset.sha256}});this.status='已安排转场';this.protected();this.update()}

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
   for(const asset of [a.native,b.native,plan.asset]){await this.cache.load(asset);if(token!==this.starting||this.dead)return}
   const at=this.ctx.currentTime+.08,offset=Math.max(0,position-4)
   this.active=this.graph(a,at,offset);this.source(this.active,this.cache.buffers.get(a.native.url)!,at,offset);this.active.gain.gain.setValueAtTime(0,at);this.active.gain.gain.linearRampToValueAtTime(.76,at+.02)
   this.paused=false;this.log('track_start',{track:a.id,sourceOffset:offset,scheduledAt:at,assetSha256:a.native.sha256})
   this.log('comparison_started',{requestId,experiment,plan,sourcePlaybackStart:offset,virtualTriggerSourceSec:position,virtualTriggerContextSec:at+position-offset,cacheProtocol:'A、B和进入素材全部就绪后开始；关闭自动接歌与背景预加载'})
   this.schedule(plan,at+position-offset,{kind:'next',targetId:b.id},requestId,{best:plan,candidates:[plan],rejected:[],exclusions:[]})
   this.comparisonEnd=at+(plan.end-offset)+8;this.protected()
  }catch(e){if(token===this.starting){this.outcome(requestId,'failed',(e as Error).message);this.stop();this.status=(e as Error).message}throw e}
  finally{if(token===this.starting){this.busy=false;this.update()}}
 }
 private async prewarm(){if(this.comparisonMode)return;const a=this.active;if(!a)return;const revision=this.starting;const intents:Intent[]=[{kind:'next'},{kind:'style',style:a.track.style==='Trap'?'Grime':'Trap'}];for(const intent of intents){if(this.pending||this.busy||this.active!==a||revision!==this.starting)return;const p=planNext(a.track,this.tracks,Math.max(this.position,(a.track.bars[0]||0)+1),intent,this.cache.ready,30,false).best;if(!p)continue;try{const b=this.tracks.find(t=>t.id===p.to)!;await this.cache.load(b.native);if(this.active!==a||this.pending)return;await this.cache.load(p.asset)}catch(e){this.log('prewarm_failed',{message:(e as Error).message})}}this.update()}
 export(){return {schema:'harbeat.v3_live_session.v2',sessionId:this.sessionId,policy:DECISION_POLICY,retention:'完整事件自动保存在同源同浏览器 IndexedDB；仍可导出，不上传服务器。清理站点数据会删除本地记录。',catalog:this.tracks.map(t=>({id:t.id,title:t.title,reportId:t.reportId,provenance:t.provenance,native:t.native,style:t.style,styleScore:t.styleScore,warnings:t.warnings,mixProfile:t.mixProfile})),sampleRate:this.ctx.sampleRate,baseLatency:this.ctx.baseLatency,outputLatency:this.ctx.outputLatency,logs:this.logs,limitations:['Audio observations locate render quanta, not physical source onset/speaker output','Single-song tempo assets were prepared ahead; selection/EQ/fade/mixing run live','Browser DSP is not bit-identical to FFmpeg V3','Energy uses common dBFS RMS, not validated perceived energy; all structural candidates need listening confirmation']}}
 dispose(){this.dead=true;this.stop();window.removeEventListener?.('pagehide',this.flushSession);this.flushSession();clearInterval(this.timer);this.cache.dispose();void this.ctx.close()}
}
