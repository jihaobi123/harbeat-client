import {describe,it,expect,vi,afterEach} from 'vitest'
import {LiveTransport} from './transport'
import {validateSession} from './sessionStore'
import {executionRows} from '../analysis/MixTracePanel'
import {Track} from './planner'
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
 const p=await setup();await p.request({kind:'next'},10);const plan=p.pending!.plan;p.stop();let release:any;p.cache.load=vi.fn(()=>new Promise<AudioBuffer>(r=>release=r));
 const task=p.playComparison(plan,50,{experimentId:'vocal',arm:'baseline',midDb:-5});await Promise.resolve();p.stop();release({duration:120});await task;expect(p.active).toBeNull();expect(p.pending).toBeNull()
})
