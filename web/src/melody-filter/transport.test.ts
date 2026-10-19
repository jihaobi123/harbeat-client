import {afterEach,expect,it,vi} from 'vitest'
import {MelodyFilterPlayer,type MelodyFilterCase,type State} from './transport'
class Param{value=0;points:any[]=[];setValueAtTime(...x:any[]){this.points.push(x)}linearRampToValueAtTime(...x:any[]){this.points.push(x)}exponentialRampToValueAtTime(...x:any[]){this.points.push(x)}cancelScheduledValues(){}setTargetAtTime(){}}
class Node{gain=new Param();frequency=new Param();Q=new Param();buffer:any;onended:any;type='';targets:Node[]=[];connect(n:Node){this.targets.push(n)}disconnect(){}start(...args:any[]){started.push({args,node:this})}stop(){stopped.push(this)}}
const started:{args:any[];node:Node}[]=[],stopped:Node[]=[],filters:Node[]=[]
class Context{currentTime=0;sampleRate=44100;state='running';destination=new Node();audioWorklet={addModule:async()=>{}};createGain(){return new Node()}createBiquadFilter(){const n=new Node();filters.push(n);return n}createBufferSource(){return new Node()}async resume(){}async close(){}}
const worklets:Worklet[]=[]
class Worklet extends Node{port:{postMessage:ReturnType<typeof vi.fn>;onmessage:null|((e:{data:any})=>void)}={postMessage:vi.fn(),onmessage:null};constructor(){super();worklets.push(this)}}
let player:MelodyFilterPlayer|undefined
afterEach(()=>{player?.dispose();started.length=0;stopped.length=0;filters.length=0;worklets.length=0;vi.useRealTimers();vi.unstubAllGlobals()})
function example():MelodyFilterCase{
 const keys=['aMaster','aOther','bEntryMaster','bEntryOther','bBodyMaster','bBodyOther']
 const assets=Object.fromEntries(keys.map(key=>[key,{url:key,sha256:key,duration:key.startsWith('a')?8:key.startsWith('bEntry')?4:8,bytes:1}]))
 return {id:'case',aTitle:'a',bTitle:'b',pre:4,post:8,filter:{type:'highpass',startHz:20,endHz:1800,Q:Math.SQRT1_2,edgeSeconds:.02,sourceStart:12,sourceBar:{start:12,end:14,beats:[12,12.5,13,13.5],valid:true}},bpm:[107,106],planSha256:'frozen',assets,features:{},sourceVerification:{},plan:{id:'plan',start:10,end:14,duration:4,rate:1,window:{start:20,end:24,bars:2},v30Eq:{a:[{t:0,low:-9,mid:0,high:-1.4}],b:[{t:0,low:-7,mid:0,high:1.2}]}}} as unknown as MelodyFilterCase
}
async function setup(change:(s:State)=>void=()=>{}){vi.useFakeTimers();vi.stubGlobal('window',{setInterval,clearInterval});vi.stubGlobal('AudioContext',Context);vi.stubGlobal('AudioWorkletNode',Worklet);player=new MelodyFilterPlayer(new URL('https://example.test/'),change);await player.initialize();player.cache!.load=vi.fn(async asset=>({key:asset.url,duration:asset.duration,length:asset.duration*44100,numberOfChannels:2} as unknown as AudioBuffer));return player}
function onsetEvent(){const message=worklets.at(-1)!.port.postMessage.mock.calls.filter(([m])=>m.kind==='arm').at(-1)![0];return {...message.events.find((e:any)=>e.name==='试听开始'),observedFrame:4480,quantumStart:4352,quantumFrames:128,late:0}}
function observe(data:any){worklets.at(-1)!.port.onmessage!({data})}
it('uses six identical sources and EQ, preserving original vocal gains while changing only outgoing other highpass correction',async()=>{
 const p=await setup(),c=example(),raw=JSON.stringify(c);await p.play(c,'natural',{roundId:'round',letter:'A'});const a=p.logs.find(x=>x.kind==='melody_filter_started');await p.play(c,'relay',{roundId:'round',letter:'B'});const b=p.logs.filter(x=>x.kind==='melody_filter_started').at(-1)
 expect(a.assets).toEqual(b.assets);expect(a.plan).toEqual(b.plan);expect(a.eq).toEqual(b.eq);expect(a.treatment.a).toEqual(b.treatment.a);expect(a.treatment.b).toEqual(b.treatment.b);expect(a.treatment).not.toEqual(b.treatment);expect(started.slice(0,6).map(x=>(x.node.buffer as any).key)).toEqual(['aMaster','aOther','bEntryMaster','bBodyMaster','bEntryOther','bBodyOther']);expect(started.slice(-6).map(x=>(x.node.buffer as any).key)).toEqual(['aMaster','aOther','bEntryMaster','bBodyMaster','bEntryOther','bBodyOther'])
 expect(started).toHaveLength(12);expect(p.cache!.load).toHaveBeenCalledTimes(12);expect(started.slice(-6).filter(x=>x.args[0]===8.1)).toHaveLength(2);expect(filters).toHaveLength(26);const hp=filters.filter(x=>x.type==='highpass');expect(hp).toHaveLength(2);expect(hp[1].Q.value).toBeCloseTo(20*Math.log10(Math.SQRT1_2),12);expect(hp[1].frequency.points.at(-1)).toEqual([1800,8.1]);expect(JSON.stringify(c)).toBe(raw)
})
it('cancels loading without scheduling sources or completion',async()=>{
 const p=await setup();let resolve!:(b:AudioBuffer)=>void;const wait=new Promise<AudioBuffer>(r=>resolve=r);p.cache!.load=vi.fn(()=>wait);const play=p.play(example(),'relay');await Promise.resolve();await Promise.resolve();p.stop();resolve({} as AudioBuffer);await play;expect(started).toHaveLength(0);expect(p.logs.some(x=>x.kind==='melody_filter_finished')).toBe(false)
})
it('attributes rendered onset and one completion to the replacement arm',async()=>{
 const p=await setup();await p.play(example(),'relay',{roundId:'old',letter:'B'});const stale=onsetEvent();await p.play(example(),'natural',{roundId:'new',letter:'A'});observe(stale);expect(p.state.status).toBe('loading');observe(onsetEvent());expect(p.state.status).toBe('playing');const end=worklets.at(-1)!.port.postMessage.mock.calls.filter(([m])=>m.kind==='arm').at(-1)![0].events.find((e:any)=>e.name==='试听结束');observe({...end,observedFrame:end.frame});(p.ctx as unknown as Context).currentTime=21;vi.advanceTimersByTime(240);expect(p.logs.filter(x=>x.kind==='melody_filter_finished')).toHaveLength(1);expect(p.logs.find(x=>x.kind==='melody_filter_finished')).toMatchObject({roundId:'new',letter:'A'});expect(stopped).toHaveLength(12)
})
it('rejects added FX, shifted buffers and unsafe bridge bounds',async()=>{
 const p=await setup(),c=example();c.assets.aEcho={...c.assets.aOther};await p.play(c,'relay');expect(p.state.status).toBe('error');expect(p.cache!.load).not.toHaveBeenCalled();const invalid=example();invalid.filter.sourceStart+=1;await p.play(invalid,'natural');expect(p.state.status).toBe('error');const load=p.cache!.load;p.cache!.load=vi.fn(async(a,s)=>({...await load(a,s),length:1} as AudioBuffer));await p.play(example(),'relay');expect(p.state.status).toBe('error');expect(started).toHaveLength(0)
})
it('preserves distinct durable player identities',async()=>{const p=await setup(),vocal=new MelodyFilterPlayer(new URL('https://example.test/'),()=>{});expect(p.recordId).not.toBe(vocal.recordId);vocal.dispose()})
it('fails visibly when the audio clock never reports rendered onset, then permits retry',async()=>{
 const p=await setup();await p.play(example(),'relay',{roundId:'practice',letter:'B'});expect(p.state.status).toBe('loading');vi.advanceTimersByTime(5200);expect(p.state.status).toBe('error');expect(p.logs.find(x=>x.kind==='melody_filter_failed')).toMatchObject({reason:'render-onset-timeout',audioContextState:'running'});expect(p.logs.some(x=>x.kind==='melody_filter_finished')).toBe(false);expect(stopped).toHaveLength(6)
 await p.play(example(),'relay',{roundId:'practice',letter:'B'});observe(onsetEvent());expect(p.state.status).toBe('playing')
})
it('fails clearly if resumed context is not running before any sources are scheduled',async()=>{
 const p=await setup();(p.ctx as unknown as Context).state='suspended';await p.play(example(),'natural');expect(p.state.status).toBe('error');expect(started).toHaveLength(0);expect(p.logs.some(x=>x.kind==='melody_filter_finished')).toBe(false)
})
it('does not mark heard from wall-clock progress if rendered end is missing',async()=>{
 const p=await setup();await p.play(example(),'natural',{roundId:'round',letter:'A'});observe(onsetEvent());(p.ctx as unknown as Context).currentTime=16.3;vi.advanceTimersByTime(80);expect(p.state.status).not.toBe('complete');expect(p.logs.some(x=>x.kind==='melody_filter_finished')).toBe(false);(p.ctx as unknown as Context).currentTime=17;vi.advanceTimersByTime(80);expect(p.state.status).toBe('error');expect(p.logs.at(-1)).toMatchObject({kind:'melody_filter_failed',reason:'render-end-timeout'})
})
