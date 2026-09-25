import {describe,it,expect,vi,afterEach} from 'vitest'
import {LiveTransport} from './transport'
import {validateSession} from './sessionStore'
import {executionRows} from '../analysis/MixTracePanel'
import {Track,planNext} from './planner'
class Param{value=0;events:any[]=[];setValueAtTime(v:number,t:number){this.events.push(['set',v,t]);this.value=v}linearRampToValueAtTime(v:number,t:number){this.events.push(['ramp',v,t])}cancelAndHoldAtTime(t:number){this.events.push(['cancel',t])}cancelScheduledValues(){}setTargetAtTime(){}}
class Node{gain=new Param();frequency=new Param();Q=new Param();type='';buffer:any;starts:any[]=[];stops:any[]=[];connect(){}disconnect(){}start(...x:any[]){this.starts.push(x)}stop(...x:any[]){this.stops.push(x)}}
class Context{currentTime=0;sampleRate=44100;state='running';baseLatency=.01;outputLatency=.01;destination=new Node();audioWorklet={addModule:async()=>{}};createGain(){return new Node()}createBufferSource(){return new Node()}createBiquadFilter(){return new Node()}async resume(){this.state='running'}async suspend(){this.state='suspended'}async close(){}}
class Worklet extends Node{port={postMessage:vi.fn(),onmessage:null}}
function t(id:string):Track{return {id,title:id,bpm:100,style:'Trap',styleScore:.5,duration:120,native:{url:id+'.flac',sha256:'x',bytes:1,duration:120},bars:Array.from({length:50},(_,i)=>i*2.4),sections:[{start:0,end:120,label:'verse'}],vocals:[[0,120]],energy:[{start:0,end:120,value:.5}],windows:[{id:'w',start:0,end:4.8,bars:2,role:'verse',energy:.5,variants:{a:{url:'clip.flac',sha256:'x',bytes:1,duration:4.8,rate:1}}}]}}
const instances:LiveTransport[]=[]
async function setup(){vi.useFakeTimers();vi.stubGlobal('window',{setInterval,clearInterval});vi.stubGlobal('AudioContext',Context);vi.stubGlobal('AudioWorkletNode',Worklet);const p=new LiveTransport([t('a'),t('b')],()=>{},new URL('https://example.test/'));instances.push(p);await p.initialize();p.cache.load=vi.fn(async asset=>{const buffer={duration:asset.duration,length:44100*asset.duration,numberOfChannels:2} as AudioBuffer;p.cache.buffers.set(asset.url,buffer);return buffer});await p.start('a',50);await Promise.resolve();p.cache.buffers.set('b.flac',{} as AudioBuffer);p.cache.buffers.set('clip.flac',{} as AudioBuffer);return p}
afterEach(()=>{instances.splice(0).forEach(p=>p.dispose());vi.useRealTimers();vi.unstubAllGlobals()})
describe('live request lifecycle',()=>{
 it('schedules two source clocks, V3 fade and wet/dry restore in advance',async()=>{const p=await setup();await p.request({kind:'next'},10);const pending=p.pending!;expect(pending.start).toBeGreaterThan(.2);expect((pending.deck.sources[0] as any).starts[0][0]).toBe(pending.start);expect((pending.deck.sources[1] as any).starts[0]).toEqual([pending.end,4.8]);expect((pending.deck.gain.gain as any).events).toContainEqual(['ramp',.76,pending.end]);expect(pending.deck.mid.gain.value).toBe(-5)})
 it('cancel before lock stops prepared B and clears future A fades',async()=>{const p=await setup();await p.request({kind:'next'},10);const deck=p.pending!.deck;expect(p.cancel()).toBe(true);expect(p.pending).toBeNull();expect((deck.sources[0] as any).stops.length).toBeGreaterThan(0);expect((p.active!.gain.gain as any).events.some((x:any)=>x[0]==='cancel')).toBe(true)})
 it('ordinary request during mixing is deferred and does not tear down decks',async()=>{const p=await setup();await p.request({kind:'next'},10);const pending=p.pending!;(p.ctx as any).currentTime=pending.start+.1;await p.request({kind:'up'});expect(p.pending).toBe(pending);expect(p.gate.deferred).toEqual({kind:'up'});expect(p.cancel()).toBe(false)})
 it('cancelling initial preparation never starts audio when the download finishes',async()=>{const p=await setup();p.stop();let finish:any;p.cache.load=vi.fn(()=>new Promise<AudioBuffer>(r=>{finish=r}));const task=p.start('b');await Promise.resolve();expect(p.busy).toBe(true);expect(p.cancel()).toBe(true);finish({duration:120});await task;expect(p.active).toBeNull();expect(p.busy).toBe(false)})
 it('keeps the original deadline for a request deferred during mixing',async()=>{const p=await setup();await p.request({kind:'next'},10);const pending=p.pending!;(p.ctx as any).currentTime=pending.start+.1;const clicked=p.ctx.currentTime;await p.request({kind:'up'},10);const spy=vi.spyOn(p,'request');(p.ctx as any).currentTime=pending.end+.01;(p as any).sync();expect(spy).toHaveBeenCalledWith({kind:'up'},10-(p.ctx.currentTime-clicked),{resumeId:p.logs.find(x=>x.kind==='request_received'&&x.intent.kind==='up')!.requestId})})
 it('a stop during asynchronous loading prevents later installation',async()=>{const p=await setup();let finish:any;p.cache.buffers.clear();p.cache.load=vi.fn(()=>new Promise<AudioBuffer>(r=>{finish=r}));const task=p.request({kind:'next'},10);p.stop();finish({duration:120});await task;expect(p.pending).toBeNull();expect(p.active).toBeNull();expect(p.busy).toBe(false)})
})

describe('complete request audit',()=>{
 it('links the request, all searches, chosen rationale and audio events',async()=>{
  const p=await setup();await p.request({kind:'next'},10)
  const received=p.logs.find(x=>x.kind==='request_received')!;expect(received).toBeDefined()
  const scheduled=p.logs.find(x=>x.kind==='plan_scheduled')!
  expect(scheduled.requestId).toBe(received.requestId)
  expect(scheduled.plan.decision.cues.aExit.sourceSec).toBe(scheduled.plan.end)
  expect(scheduled.selection.candidateCount).toBeGreaterThan(0)
  expect(scheduled.events.every((x:any)=>x.requestId===received.requestId)).toBe(true)
  p.cancel();expect(p.logs.some(x=>x.kind==='request_outcome'&&x.requestId===received.requestId&&x.outcome==='cancelled')).toBe(true)
 })
 it('logs failed and rejected triggers with search evidence',async()=>{
  const p=await setup();await p.request({kind:'style',style:'Missing'},10)
  const received=p.logs.find(x=>x.kind==='request_received')!;expect(received).toBeDefined()
  expect(p.logs.some(x=>x.kind==='decision_search'&&x.requestId===received.requestId&&x.result.exclusions.length)).toBe(true)
  expect(p.logs.some(x=>x.kind==='request_outcome'&&x.requestId===received.requestId&&x.outcome==='failed')).toBe(true)
  p.stop();await p.request({kind:'next'});expect(p.logs.at(-1)?.outcome).toBe('rejected')
 })
 it('keeps historical events past the old 1500-event cap and snapshots payloads',async()=>{
  const p=await setup();const data={reason:'original'};p.log('snapshot',data);data.reason='changed'
  for(let i=0;i<1600;i++)p.log('extra',{i})
  expect(p.export().logs.find((x:any)=>x.kind==='snapshot')?.reason).toBe('original')
 })
})

describe('audit terminal paths',()=>{
 it('retains one request id across deferral and records overwritten requests',async()=>{
  const p=await setup();await p.request({kind:'next'},10);const first=p.pending!;(p.ctx as any).currentTime=first.start+.1
  await p.request({kind:'up'},10);const overwritten=p.logs.filter(x=>x.kind==='request_received').at(-1)!.requestId
  await p.request({kind:'next'},10);const continued=p.logs.filter(x=>x.kind==='request_received').at(-1)!.requestId
  expect(p.logs.some(x=>x.kind==='request_outcome'&&x.requestId===overwritten&&x.outcome==='superseded')).toBe(true)
  ;(p.ctx as any).currentTime=first.end+.01;(p as any).sync();await Promise.resolve()
  expect(p.logs.filter(x=>x.kind==='request_received')).toHaveLength(3)
  expect(p.logs.some(x=>x.kind==='request_resumed'&&x.requestId===continued)).toBe(true)
  expect(p.logs.filter(x=>x.kind==='request_outcome'&&x.requestId===first.requestId)).toHaveLength(1)
 })
 it('records deferred expiration with the original request id',async()=>{
  const p=await setup();await p.request({kind:'next'},10);const first=p.pending!;(p.ctx as any).currentTime=first.start+.1
  await p.request({kind:'up'},.1);const id=p.logs.filter(x=>x.kind==='request_received').at(-1)!.requestId
  ;(p.ctx as any).currentTime=first.end+.01;(p as any).sync()
  expect(p.logs.some(x=>x.kind==='request_outcome'&&x.requestId===id&&x.outcome==='expired')).toBe(true)
 })
 it('records load failure after provisional selection',async()=>{
  const p=await setup();p.cache.buffers.clear();p.cache.load=vi.fn(async()=>{throw new Error('network unavailable')})
  await p.request({kind:'next'},10)
  const id=p.logs.find(x=>x.kind==='request_received')!.requestId
  expect(p.logs.some(x=>x.kind==='preparation_started'&&x.requestId===id&&x.provisionalDecision)).toBe(true)
  expect(p.logs.some(x=>x.kind==='request_outcome'&&x.requestId===id&&x.reason==='network unavailable')).toBe(true)
 })
})

it('exports a persistable real session and resolves planned times from audio frames',async()=>{
 const p=await setup();await p.request({kind:'next'},10);const snapshot=p.export();
 expect(validateSession(snapshot).catalog[0].title).toBe('a');
 const row=executionRows(snapshot.logs,snapshot.sampleRate)[0];
 expect(row.planned).toBeCloseTo(p.pending!.start,4);expect(row.actual).toBeNull();
})

it('plays a fixed comparison using unchanged cue times and only the requested mid EQ',async()=>{
 const p=await setup();await p.request({kind:'next'},10);const plan=JSON.parse(JSON.stringify(p.pending!.plan));p.stop();
 await p.playComparison(plan,50,{experimentId:'eq',arm:'variant',midDb:-8});
 expect(p.pending!.deck.mid.gain.value).toBe(-8);expect(p.pending!.plan.start).toBe(plan.start);expect(p.pending!.plan.end).toBe(plan.end)
 expect(p.logs.some(x=>x.kind==='comparison_started'&&x.experiment.arm==='variant')).toBe(true)
 p.stop();await p.start('a',50);await p.request({kind:'next'},10);expect(p.pending!.deck.mid.gain.value).toBe(-5)
})
it('never starts a cancelled comparison after assets finish loading',async()=>{
 const p=await setup();await p.request({kind:'next'},10);const plan=p.pending!.plan;p.stop();const releases:((b:AudioBuffer)=>void)[]=[];p.cache.load=vi.fn(()=>new Promise<AudioBuffer>(r=>releases.push(r)));
 const task=p.playComparison(plan,50,{experimentId:'vocal',arm:'baseline',midDb:-5});await Promise.resolve();p.stop();expect(releases).toHaveLength(3);releases.forEach(r=>r({duration:120} as AudioBuffer));await task;expect(p.active).toBeNull();expect(p.pending).toBeNull()
})

it('a protected planner rejection keeps A playing and never falls back',async()=>{
 const p=await setup();const active=p.active;(p as any).options={planner:()=>({best:null,candidates:[],rejected:[{track:'a',reason:'exit unreviewed'}],exclusions:[{trackId:'a',track:'a',code:'exit_unreviewed',reason:'exit unreviewed',count:1}]}),autoNext:false,prewarm:false};
 await p.request({kind:'next'},100);expect(p.active).toBe(active);expect(p.pending).toBeNull();expect(p.logs.some(x=>x.kind==='decision_search'&&x.result.exclusions.some((e:any)=>e.code==='exit_unreviewed'))).toBe(true)
})
it('protected approved plan starts only backing before takeover, keeps A to the verified exit and records protected policy',async()=>{
 const {guardPlan}=await import('../guarded/planner');const p=await setup();const [a,b]=p.tracks;a.provenance={masterSha256:'master-a'};a.sections=[{start:0,end:60,label:'verse'}];b.sections=[{start:0,end:12,label:'intro'}];const catalog={tracks:p.tracks,evidence:{a:{exits:[{id:'x',start:0,sectionEnd:60,cut:60,label:'verse'}],windows:{}},b:{exits:[],windows:{w:{start:0,end:4.8,sectionStart:0,sectionEnd:12,lane:'instrumental' as const,sourceHashes:['d','b','o']}}}}};const reviews={exits:{'a:x':{masterSha256:'master-a',cut:60,confirmedAt:'test-only',phraseEnded:true}},entries:{'b:w:a':{assetSha256:'x',bodySha256:'x',confirmedAt:'test-only',noVocalEntry:true,bodyStartsClean:true}}};
 ;(p as any).options={planner:(...args:any[])=>guardPlan(catalog,reviews,...args as [any,any,any,any,any,any]),autoNext:false,prewarm:false,policyVersion:'protected-v1'};await p.request({kind:'next'},70);const plan=p.pending!;expect(plan.plan.end).toBe(60);expect((plan.deck.sources[0] as any).starts[0][0]).toBe(plan.start);expect((plan.deck.sources[1] as any).starts[0]).toEqual([plan.end,4.8]);expect((p.active!.gain.gain as any).events).toContainEqual(['ramp',0,plan.end]);expect(plan.deck.mid.gain.value).toBe(0);expect(p.logs.filter(l=>l.kind==='decision_search').at(-1)!.policyVersion).toBe('protected-v1');expect((p.export().policy as any).version).toBe('protected-v1');expect(p.logs.find(l=>l.kind==='plan_scheduled')!.plan.protection.exitReview.phraseEnded).toBe(true)
})

it('records immutable per-request evidence and exports the exact runtime preprocessing inputs',async()=>{
 const p=await setup();await p.request({kind:'next'},10);const event=p.logs.find(e=>e.kind==='plan_scheduled')!;
 expect(event.trace.a.vocals.fraction).toBeCloseTo(event.plan.aVocal);expect(event.trace.strategy.actualBMidDb).toBe(-5);
 expect(event.trace.a.binding).toBe('missing_snapshot');const recorded=JSON.stringify(event.trace);p.tracks[0].vocals!.push([500,600]);expect(JSON.stringify(event.trace)).toBe(recorded);
 const snapshot=p.export();expect(snapshot.catalog[0].bars).toEqual(p.tracks[0].bars);expect(snapshot.catalog[0].windows).toEqual(p.tracks[0].windows);expect(snapshot.catalog[0].vocals).toEqual(p.tracks[0].vocals);
})
it('short audition skips waiting only, preserving both cue times and original trigger evidence',async()=>{
 const p=await setup();await p.request({kind:'next'},10);const plan=p.pending!.plan;p.stop();
 await p.playComparison(plan,0,{experimentId:'v31',arm:'variant',midDb:-5,skipWaiting:true});
 expect(p.active!.offset).toBe(Math.max(0,plan.start-4));expect(p.pending!.plan).toBe(plan);
 const event=p.logs.filter(x=>x.kind==='comparison_started').at(-1)!;
 expect(event.virtualTriggerSourceSec).toBe(0);expect(event.virtualTriggerContextSec).toBeNull();expect(event.skippedWaitingSec).toBeGreaterThan(0)
})

it('executes phrase gain hold and EQ points on the audio clock, retaining request-linked observations',async()=>{
 const p=await setup();await p.request({kind:'next'},10);const original=p.pending!.plan;p.cancel();
 const fade=original.end-1,plan={...original,phrase:{exit:{lastBeat:original.end-.6,tailEnd:fade},fadeStart:fade,incomingVocalRender:fade+.1,vocalGap:.1} as any,automation:{version:'phrase-automation-v1' as const,kind:'adaptive' as const,aGain:[{t:0,value:1},{t:original.duration-1,value:1},{t:original.duration,value:0}],bGain:[{t:0,value:0},{t:original.duration,value:1}],aEq:[{t:0,low:0,mid:0,high:0},{t:original.duration,low:0,mid:0,high:0}],bEq:[{t:0,low:0,mid:0,high:0},{t:2,low:-3,mid:-1,high:-.5},{t:original.duration,low:0,mid:0,high:0}],evidence:[],limitations:[]}}
 await p.playComparison(plan,50,{experimentId:'phrase-test',arm:'variant',midDb:-5});const pending=p.pending!,at=pending.start,ae=(p.active!.gain.gain as any).events,be=(pending.deck.low.gain as any).events
 expect(ae).toContainEqual(['ramp',.76,at+original.duration-1]);expect(ae).toContainEqual(['ramp',0,pending.end]);expect(be).toContainEqual(['ramp',-3,at+2]);expect(be).toContainEqual(['ramp',0,pending.end]);
 const scheduled=p.logs.filter(e=>e.kind==='plan_scheduled').at(-1)!,curve=p.logs.find(e=>e.kind==='phrase_automation')!
 expect(curve.planId).toBe(scheduled.planId);expect(curve.requestId).toBe(scheduled.requestId);expect(scheduled.events.find((e:any)=>e.name.startsWith('A 尾音')).frame).toBe(Math.round((at+original.duration-1)*p.ctx.sampleRate));
 expect(p.cancel()).toBe(true);expect(p.pending).toBeNull();expect((p.active!.dry.gain as any).events.at(-1)[1]).toBe(1)
})

it('V30 dynamic coefficients preserve every V3 gain, wet/dry event and source clock',async()=>{
 const p=await setup();await p.request({kind:'next'},10);const plan=p.pending!.plan;p.stop();
 await p.playComparison(plan,50,{experimentId:'v30',arm:'baseline',midDb:-5});
 const events=(d:any)=>JSON.parse(JSON.stringify(['gain','wet','dry'].map(k=>d[k].gain.events)));
 const original={a:events(p.active),b:events(p.pending!.deck),start:p.pending!.start,end:p.pending!.end};p.stop();
 const eq={version:'v30-eq-only-v1',a:[{t:0,low:-9,mid:0,high:-1.4},{t:4.8,low:-10,mid:0,high:-2}],b:[{t:0,low:-7,mid:-5,high:1.2},{t:4.8,low:-8,mid:-6,high:0}],template:{a:{low:-9,mid:0,high:-1.4},b:{low:-7,mid:-5,high:1.2}},evidence:[],sources:{},limits:{lowHighDb:3,midDb:2,slewDbPerSec:3},limitations:[]} as const;
 await p.playComparison({...plan,v30Eq:eq as any},50,{experimentId:'v30',arm:'variant',midDb:-5});
 expect(events(p.active)).toEqual(original.a);expect(events(p.pending!.deck)).toEqual(original.b);
 expect(p.pending!.start).toBe(original.start);expect(p.pending!.end).toBe(original.end);
 expect((p.pending!.deck.low.gain as any).events.some((e:any)=>e[0]==='ramp'&&e[1]===-8)).toBe(true);
 expect(p.logs.some(l=>l.kind==='v30_eq_automation')).toBe(true);
 p.cancel();expect((p.active!.low.gain as any).events.at(-1)[1]).toBe(0);
})

it('reports the distinct highest-ranked alternative when correction chooses rank two',async()=>{
 const p=await setup(),result=planNext(p.current!,p.tracks,50,{kind:'next'},p.cache.ready,18);
 expect(result.candidates.length).toBeGreaterThan(1);
 (p as any).schedule(result.candidates[1],0,{kind:'next'},'corrected',result);
 const e=p.logs.filter(l=>l.kind==='plan_scheduled').at(-1)!;
 expect(e.selection.chosenRank).toBe(2);expect(e.selection.runnerUp.id).toBe(result.candidates[0].id);
 expect(e.selection.runnerUp.id).not.toBe(e.plan.id);
})

it('exports vocal-overlap ranking evidence while retaining the full linear handoff',async()=>{
 const {planVocalOverlap}=await import('../vocal-overlap/planner');const p=await setup()
 for(const track of p.tracks){track.reportId='r';track.provenance={masterSha256:'m',reportSha256:'r',vocalSha256:'v',runId:'run'};track.alignment={schema:'x',status:'candidate',source:{reportId:'r',masterSha256:'m',reportSha256:'r',vocalSha256:'v'},bars:[],phrases:[],exits:[],conflicts:[],bandFrames:[{start:0,end:120,rmsDbfs:-15,low:-20,mid:-22,high:-30}],limitations:[]};track.preprocessing={schema:'harbeat.preprocessing-evidence.v1',reportId:'r',reportSha256:'r',masterSha256:'m',reportSnapshotUrl:'report.json',bindingChecks:{reportHash:true,masterHash:true},sections:{items:[]},beatGrid:{bars_ms:[],beats_ms:[]},tempo:{},vocalActivity:{status:'ready',time_origin:'master_audio_start',unit:'ms',source:{track_id:track.id,analysis_run_id:'run',vocal_sha256:'v'},intervals:[{start_ms:0,end_ms:120000}]},vocalRms:{points:[]},energy:{},genre:{},extensions:[]}}
 ;(p as any).options={planner:planVocalOverlap,autoNext:false,prewarm:false,policyVersion:'vocal-overlap-v1'}
 await p.request({kind:'next'},18)
 const scheduled=p.logs.find(e=>e.kind==='plan_scheduled')!,search=p.logs.filter(e=>e.kind==='decision_search').at(-1)!
 expect(search.result.selectedVocalOverlap.version).toBe('vocal-overlap-v1')
 expect(search.result.candidates[0].vocalOverlap.weightedOverlap).toBeCloseTo(1)
 expect(p.export().policy.ranking).toContain('gain-weighted')
 expect(scheduled.selection.strategyReason).toContain('人声评分')
 expect(scheduled.trace.mode).toBe('vocal-overlap-dynamic')
 expect(scheduled.trace.strategy.actualBMidDb).toBeNull()
 expect(scheduled.trace.strategy.automation).toBeUndefined()
 expect(scheduled.trace.features.find((f:any)=>f.key==='vocals').effect).toContain('加权')
 expect(scheduled.trace.vocalOverlap.weightedOverlap).toBeCloseTo(1)
 expect((p.active!.gain.gain as any).events).toContainEqual(['set',.76,p.pending!.start])
 expect((p.active!.gain.gain as any).events).toContainEqual(['ramp',0,p.pending!.end])
 expect((p.pending!.deck.gain.gain as any).events).toContainEqual(['ramp',.76,p.pending!.end])
})

async function segmented(){const p=await setup();(p as any).options={autoNext:false,prewarm:false};for(const track of p.tracks){track.duration=240;track.native.duration=150;track.bars=Array.from({length:100},(_,i)=>i*2.4);track.sections=[{start:0,end:240,label:'verse'}];track.vocals=[[0,240]];track.energy=[{start:0,end:240,value:.5}];track.windows[0].variants.b={...track.windows[0].variants.a,url:track.id+'-clip.flac'};track.audioSegments=[{start:0,end:150,asset:track.native},...Array.from({length:3},(_,i)=>({start:150+i*30,end:180+i*30,asset:{url:track.id+'-'+i+'.flac',sha256:'x',bytes:1,duration:30}}))]}return p}
async function drain(){for(let i=0;i<12;i++)await Promise.resolve()}
describe('continuous full-song transport',()=>{
 it('seeks into a late chunk and schedules the next one without a clock gap',async()=>{const p=await segmented();await p.start('a',181);await drain();expect((p.active!.sources[0] as any).starts[0]).toEqual([.08,1,29]);expect((p.active!.sources[1] as any).starts[0]).toEqual([29.08,0,30]);expect(p.cache.protected.has('a.flac')).toBe(false)})
 it('keeps pause intent after seek and never resumes as a side effect of preparation',async()=>{const p=await segmented();await p.togglePause();await p.seek(181);expect(p.paused).toBe(true);expect(p.ctx.state).toBe('suspended');await p.prepareNext('b');expect(p.paused).toBe(true);expect(p.ctx.state).toBe('suspended');expect(p.position).toBe(181)})
 it('prepares the selected next song while preserving the current deck and clock',async()=>{const p=await segmented();const deck=p.active;await p.prepareNext('b');expect(p.active).toBe(deck);expect(p.pending).toBeNull();expect(p.cache.ready.has('b.flac')).toBe(true);expect(p.cache.ready.has('clip.flac')).toBe(true);p.cancelPreparation();expect(p.cache.protected.has('b.flac')).toBe(false)})
 it('a stopped prefetch cannot retain pins or install a stale selection',async()=>{const p=await segmented();let complete!:(b:AudioBuffer)=>void;p.cache.load=vi.fn(()=>new Promise<AudioBuffer>(r=>complete=r));const work=p.prepareNext('b');await Promise.resolve();p.stop();complete({duration:150} as AudioBuffer);await expect(work).rejects.toMatchObject({name:'AbortError'});expect(p.cache.protected.size).toBe(0);expect(p.active).toBeNull()})
 it('suspends before a missing boundary and resumes only after verified audio is available',async()=>{const p=await segmented();await p.start('a',110);let complete!:(b:AudioBuffer)=>void;p.cache.load=vi.fn(()=>new Promise<AudioBuffer>(r=>complete=r));(p.ctx as any).currentTime=10.08;(p as any).tick();(p.ctx as any).currentTime=39.8;(p as any).tick();await drain();expect(p.buffering).toBe(true);expect(p.ctx.state).toBe('suspended');complete({duration:30} as AudioBuffer);await drain();expect(p.buffering).toBe(false);expect(p.ctx.state).toBe('running');expect((p.active!.sources[1] as any).starts[0]).toEqual([40.08,0,30])})
 it('honors a user pause while a missing chunk completes',async()=>{const p=await segmented();await p.start('a',110);let complete!:(b:AudioBuffer)=>void;p.cache.load=vi.fn(()=>new Promise<AudioBuffer>(r=>complete=r));(p.ctx as any).currentTime=10.08;(p as any).tick();(p.ctx as any).currentTime=39.8;(p as any).tick();await drain();await p.togglePause();complete({duration:30} as AudioBuffer);await drain();expect(p.paused).toBe(true);expect(p.ctx.state).toBe('suspended')})
 it('continues B into body chunks and allows another full handoff in the same session',async()=>{const p=await segmented();await p.start('a',140);await drain();await p.request({kind:'next',targetId:'b'},10);const first=p.pending!;expect(first).not.toBeNull();expect((first.deck.sources[1] as any).starts[0]).toEqual([first.end,4.8,145.2]);(p.ctx as any).currentTime=first.end+.01;(p as any).tick();await p.prepareNext('a');await p.request({kind:'next',targetId:'a'},10);expect(p.pending!.plan.to).toBe('a');expect(p.sessionId).toBe(p.logs.find(x=>x.kind==='track_start')!.sessionId)})
})


it('cancelling a mix request does not strand an independent segment buffering pause',async()=>{
 const p=await segmented();await p.start('a',110);let complete!:(b:AudioBuffer)=>void;p.cache.load=vi.fn(()=>new Promise<AudioBuffer>(r=>complete=r));(p.ctx as any).currentTime=10.08;(p as any).tick();(p.ctx as any).currentTime=39.8;(p as any).tick();p.cancel();await drain();complete({duration:30} as AudioBuffer);await drain();expect(p.buffering).toBe(false);expect(p.ctx.state).toBe('running')
})

it('replaces a stale selected-next fetch without stopping A or losing the latest pins',async()=>{
 const p=await segmented(),c=JSON.parse(JSON.stringify(p.tracks[1]));c.id='c';c.native={...c.native,url:'c.flac'};c.audioSegments[0].asset=c.native;c.windows[0].variants.a={...c.windows[0].variants.a,url:'c-clip.flac'};p.tracks.push(c)
 const active=p.active;let release!:(b:AudioBuffer)=>void
 const original=p.cache.load;p.cache.load=vi.fn((asset,signal)=>asset.url==='b.flac'?new Promise<AudioBuffer>(r=>release=r):original(asset,signal))
 const old=p.prepareNext('b'),rejected=expect(old).rejects.toMatchObject({name:'AbortError'});await Promise.resolve();await p.prepareNext('c');release({duration:150} as AudioBuffer);await rejected
 expect(p.active).toBe(active);expect(p.cache.protected.has('b.flac')).toBe(false);expect(p.cache.protected.has('c.flac')).toBe(true)
})
it('late background wakeups restore the last covered source point and log the interruption',async()=>{
 const p=await segmented();await p.start('a',110);let release!:(b:AudioBuffer)=>void
 const original=p.cache.load;p.cache.load=vi.fn((asset,signal)=>asset.url==='a-0.flac'?new Promise<AudioBuffer>(r=>release=r):original(asset,signal))
 ;(p.ctx as any).currentTime=10.08;(p as any).tick();(p.ctx as any).currentTime=41;(p as any).tick();await drain()
 p.cache.load=original;release({duration:30} as AudioBuffer);await drain()
 expect(p.logs.some(l=>l.kind==='segment_deadline_missed'&&l.resumeSourceSec===150)).toBe(true);expect(p.position).toBe(150);expect(p.active?.track.id).toBe('a')
})
it('stop prevents a buffering completion from resuming the audio context',async()=>{
 const p=await segmented();await p.start('a',110);let complete!:(b:AudioBuffer)=>void;p.cache.load=vi.fn(()=>new Promise<AudioBuffer>(r=>complete=r));(p.ctx as any).currentTime=10.08;(p as any).tick();(p.ctx as any).currentTime=39.8;(p as any).tick();await drain();p.stop();complete({duration:30} as AudioBuffer);await drain();expect(p.ctx.state).toBe('suspended');expect(p.active).toBeNull();expect(p.cache.protected.size).toBe(0)
})

it('loads the correct B body chunk when an entry ends exactly at the prefix boundary',async()=>{
 const p=await segmented(),b=p.tracks[1];b.windows[0].start=145.2;b.windows[0].end=150
 await p.request({kind:'next',targetId:'b'},10);expect(p.pending).not.toBeNull()
 const body=p.pending!.deck.sources[1] as any
 expect(body.buffer).toBe(p.cache.buffers.get('b-0.flac'));expect(body.starts[0]).toEqual([p.pending!.end,0,30])
})

it('records each full-song source range and hash at its scheduled audio-clock time',async()=>{
 const p=await segmented();await p.start('a',181);await drain();const rows=p.logs.filter(l=>l.kind==='native_segment_scheduled')
 expect(rows).toHaveLength(2);expect(rows[0]).toMatchObject({track:'a',sourceStart:181,sourceEnd:210,scheduledContextSec:.08,assetUrl:'a-1.flac',assetSha256:'x'});expect(rows[1]).toMatchObject({sourceStart:210,sourceEnd:240,scheduledContextSec:29.08})
})

it('does not pause a committed handoff for an outgoing chunk that starts after A retires',async()=>{
 const p=await segmented(),original=p.cache.load;p.tracks[0].bars=[145,149.8,154.6]
 p.cache.load=vi.fn((asset,signal)=>asset.url==='a-0.flac'?new Promise<AudioBuffer>(()=>{}):original(asset,signal));await p.start('a',140);await drain();await p.request({kind:'next',targetId:'b'},10)
 const pending=p.pending!;expect(pending).not.toBeNull();expect(pending.plan.end).toBe(149.8);(p.ctx as any).currentTime=pending.end-.1;(p as any).tick();await drain();expect(p.buffering).toBe(false);expect(p.ctx.state).toBe('running')
})

it('prepares the future automatic cue while preserving current audio and no scheduled fade',async()=>{
 const p=await setup();const active=p.active
 await p.prepareNext('b',{automatic:true})
 expect(p.automaticStart).toBeGreaterThan(80)
 expect(p.active).toBe(active);expect(p.pending).toBeNull()
 p.cancelPreparation();expect(p.automaticStart).toBeNull()
})

it('executes the prepared future plan intact, instead of reselecting within an 18-second click budget',async()=>{
 const p=await setup();await p.prepareNext('b',{automatic:true})
 const start=p.automaticStart!;expect(start).toBeGreaterThan(p.position+18)
 ;(p.ctx as any).currentTime=p.active!.at+start-p.active!.offset-8
 await p.request({kind:'next',targetId:'b'},18,{origin:'continuous_end_auto',automatic:true})
 expect(p.pending!.plan.start).toBe(start);expect(p.pending!.plan.prepared).toBe(true)
 expect(p.pending!.plan.duration).toBe(4.8)
 expect((p.active!.gain.gain as any).events).toContainEqual(['ramp',0,p.pending!.end])
 expect((p.pending!.deck.gain.gain as any).events).toContainEqual(['ramp',.76,p.pending!.end])
})
it('turning off automatic mode cancels its unlocked schedule while preserving manual handoffs',async()=>{
 const p=await setup();await p.prepareNext('b',{automatic:true});await p.request({kind:'next',targetId:'b'},18,{automatic:true})
 expect(p.pending?.automatic).toBe(true);p.cancelAutomatic();expect(p.pending).toBeNull()
 await p.request({kind:'next',targetId:'b'},18);expect(p.pending).not.toBeNull()
 p.cancelAutomatic();expect(p.pending).not.toBeNull()
})
it('seeking clears the old automatic cue and pause keeps its replacement on the paused clock',async()=>{
 const p=await setup();await p.prepareNext('b',{automatic:true});await p.togglePause();await p.seek(70)
 expect(p.automaticStart).toBeNull();expect(p.paused).toBe(true)
 await p.prepareNext('b',{automatic:true});expect(p.automaticStart).toBeGreaterThan(70)
 await p.request({kind:'next',targetId:'b'},18,{automatic:true});expect(p.pending).toBeNull()
})
it('a slow automatic preload does not publish an already missed cue',async()=>{
 const p=await setup(),load=p.cache.load;let moved=false
 p.cache.load=vi.fn(async(asset,signal)=>{const buffer=await load(asset,signal);if(!moved){(p.ctx as any).currentTime=60;moved=true}return buffer})
 await p.prepareNext('b',{automatic:true})
 expect(p.automaticStart).toBeGreaterThan(p.position+.25)
})

it('turning off automatic mode also cancels an in-flight automatic asset load',async()=>{
 const p=await setup();p.cache.buffers.clear();const load=p.cache.load;let release!:()=>void
 let first=true;p.cache.load=vi.fn(async(asset,signal)=>{if(first){first=false;await new Promise<void>(r=>release=r)}return load(asset,signal)})
 const request=p.request({kind:'next',targetId:'b'},18,{automatic:true})
 expect(p.busy).toBe(true);p.cancelAutomatic();release();await request
 expect(p.pending).toBeNull();expect(p.active?.track.id).toBe('a')
})

it('automatic shortlist prepares a winning song and a ready backup without scheduling fades',async()=>{
 const p=await setup();const {qualityTrack}=await import('../continuous/qualityFixture');const {planAutomaticQuality}=await import('../continuous/qualityPlan')
 ;(p as any).options.automaticPlanner=planAutomaticQuality
 p.tracks=['a','b','c'].map(qualityTrack);await p.start('a',0)
 const id=await p.prepareAutomatic(['b','c']);await new Promise<void>(r=>queueMicrotask(r));await new Promise<void>(r=>queueMicrotask(r))
 expect(id).toBe('b');expect(p.automaticStart).toBeGreaterThan(40);expect(p.pending).toBeNull()
 expect(p.logs.some(l=>l.kind==='automatic_backup_ready')).toBe(true)
 expect(p.cache.protected.has('c')).toBe(true)
})
it('automatic shortlist falls back on download failure and exact-song requests never substitute another song',async()=>{
 const p=await setup();const {qualityTrack}=await import('../continuous/qualityFixture');const {planAutomaticQuality}=await import('../continuous/qualityPlan')
 ;(p as any).options.automaticPlanner=planAutomaticQuality;p.tracks=['a','b','c'].map(qualityTrack);await p.start('a',0)
 const load=p.cache.load;p.cache.load=vi.fn(async(asset,signal)=>{if(asset.url==='b')throw Error('offline');return load(asset,signal)})
 expect(await p.prepareAutomatic(['b','c'])).toBe('c')
 await expect(p.prepareAutomatic(['b'])).rejects.toThrow()
 expect(p.automaticStart).toBeNull()
})
it('cancelled automatic shortlist cannot install a late result',async()=>{
 const p=await setup();const {qualityTrack}=await import('../continuous/qualityFixture');const {planAutomaticQuality}=await import('../continuous/qualityPlan')
 ;(p as any).options.automaticPlanner=planAutomaticQuality;p.tracks=['a','b'].map(qualityTrack);await p.start('a',0)
 let finish!:(value:AudioBuffer)=>void;p.cache.load=vi.fn(()=>new Promise<AudioBuffer>(r=>{finish=r}))
 const task=p.prepareAutomatic(['b']);p.cancelPreparation();finish({} as AudioBuffer)
 await expect(task).rejects.toThrow();expect(p.automaticStart).toBeNull()
})

it('an exact-song automatic request tries another entry window if the preferred clip fails',async()=>{
 const p=await setup();const {qualityTrack}=await import('../continuous/qualityFixture');const {planAutomaticQuality}=await import('../continuous/qualityPlan')
 ;(p as any).options.automaticPlanner=planAutomaticQuality;const a=qualityTrack('a'),b=qualityTrack('b')
 b.windows.push({...b.windows[0],id:'second',start:12,end:20,variants:{a:{...b.windows[0].variants.a,url:'second',sha256:'second'}}})
 p.tracks=[a,b];await p.start('a',0)
 const load=p.cache.load;p.cache.load=vi.fn(async(asset,signal)=>{if(asset.url==='clip')throw Error('bad clip');return load(asset,signal)})
 expect(await p.prepareAutomatic(['b'])).toBe('b')
 expect(p.logs.filter(l=>l.kind==='next_preparation_ready').at(-1)!.candidateId).toContain(':second:')
})

it('turning auto off preserves an already scheduled manual handoff',async()=>{
 const p=await setup();const {canPrepareAfterAutoOff}=await import('../continuous/automatic')
 await p.request({kind:'next',targetId:'b'},18);const manual=p.pending
 p.cancelAutomatic();p.cancelPreparation()
 if(canPrepareAfterAutoOff(p,'b'))p.cancel()
 expect(p.pending).toBe(manual)
})
it('automatic request audit names the actual policy without relabeling manual requests',async()=>{
 const p=await setup();const {qualityTrack}=await import('../continuous/qualityFixture');const {planAutomaticQuality,AUTOMATIC_POLICY}=await import('../continuous/qualityPlan')
 Object.assign((p as any).options,{automaticPlanner:planAutomaticQuality,automaticPolicyVersion:AUTOMATIC_POLICY,policyVersion:'vocal-overlap-v1'})
 p.tracks=['a','b'].map(qualityTrack);await p.start('a',0);await p.prepareAutomatic(['b']);await p.request({kind:'next',targetId:'b'},18,{automatic:true})
 expect(p.logs.filter(l=>l.kind==='request_received').at(-1)!.policyVersion).toBe(AUTOMATIC_POLICY)
 expect(p.logs.filter(l=>l.kind==='decision_search').at(-1)!.policyVersion).toBe(AUTOMATIC_POLICY)
 expect(p.export().automaticPolicy?.version).toBe(AUTOMATIC_POLICY)
 p.cancel();await p.request({kind:'next',targetId:'b'},18)
 expect(p.logs.filter(l=>l.kind==='request_received').at(-1)!.policyVersion).toBe('vocal-overlap-v1')
})
