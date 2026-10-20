import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {MetricTransport} from './transport'
let held:Promise<any>|null=null,heldFor:string|null=null
vi.mock('../realtime/cache',()=>({AudioCache:class{protected=new Set();constructor(..._args:any[]){}load(a:any){return held&&(!heldFor||a.url===heldFor)?held:Promise.resolve({duration:a.duration})}dispose(){}}}))
class Param{value=0;setValueAtTime(){}linearRampToValueAtTime(){}setTargetAtTime(){}}
class Node{gain=new Param();port={postMessage:vi.fn(),onmessage:null};buffer:any;onended:any;start=vi.fn();stop=vi.fn();connect(){}disconnect(){}}
class Ctx{currentTime=0;sampleRate=44100;state='running';destination=new Node();audioWorklet={addModule:async()=>{}};createGain(){return new Node()}createBufferSource(){return new Node()}async resume(){this.state='running'}async suspend(){this.state='suspended'}async close(){}}
const asset=(id:string,d=30)=>({url:'/'+id,sha256:id,duration:d,bytes:20})
const track=(id:string)=>({id,title:id,duration:60,native:asset(id),audioSegments:[{start:0,end:30,asset:asset(id)},{start:30,end:60,asset:asset(id+'2')}]}) as any
const result:any={id:'job',plan:{from:'a',to:'b',start:10,end:14,duration:4,bEnd:8},assets:{original:asset('mix',4.008)},decision:{methods:{original:{eligible:true,name:'原版'}}}}
let p:MetricTransport
beforeEach(()=>{held=null;heldFor=null;vi.useFakeTimers();vi.stubGlobal('window',globalThis);vi.stubGlobal('AudioContext',Ctx);vi.stubGlobal('AudioWorkletNode',Node);p=new MetricTransport(new URL('https://example.com/listen/'),()=>{})})
afterEach(()=>{p.dispose();vi.useRealTimers();vi.unstubAllGlobals()})
it('plays transition and adopts B on the same audio clock at its frozen source position',async()=>{
 await p.start(track('a'));await p.arm(result,'original',track('b'));expect(p.transition?.at).toBeCloseTo(10.12);expect(p.transition?.end).toBeCloseTo(14.12)
 ;(p.ctx as unknown as Ctx).currentTime=14.5;vi.advanceTimersByTime(80);expect(p.current?.id).toBe('b');expect(p.position).toBeCloseTo(8.38);expect(p.logs.some(x=>x.kind==='handoff_complete')).toBe(true)
})
it('stop during async clip preparation cannot schedule stale audio',async()=>{
 await p.start(track('a'));let release!:(v:any)=>void;held=new Promise(r=>release=r);const work=p.arm(result,'original',track('b'));p.stop();release({duration:30});await work;expect(p.current).toBe(null);expect(p.transition).toBe(null);expect(p.logs.some(x=>x.kind==='plan_scheduled')).toBe(false)
})
it('rejects a mismatched B and expired cue without interrupting A',async()=>{
 await p.start(track('a'));await expect(p.arm(result,'original',track('c'))).rejects.toThrow();(p.ctx as unknown as Ctx).currentTime=10;await expect(p.arm(result,'original',track('b'))).rejects.toThrow();expect(p.current?.id).toBe('a')
})

it('cancelling an audition load cannot arm an older plan over a newly started same song',async()=>{
 await p.initialize();let release!:(v:any)=>void;held=new Promise(r=>release=r);const work=p.audition(result,'original',track('a'),track('b'));await Promise.resolve();await Promise.resolve();p.stop();held=null;await p.start(track('a'));release({duration:30});await work;expect(p.current?.id).toBe('a');expect(p.transition).toBe(null)
})
it('preloads audition assets before starting its four-second source clock on a slow network',async()=>{
 await p.initialize();let release!:(v:any)=>void;heldFor='/mix';held=new Promise(r=>release=r);const work=p.audition(result,'original',track('a'),track('b'));for(let i=0;i<12;i++)await Promise.resolve();expect(p.current).toBe(null);(p.ctx as unknown as Ctx).currentTime=100;release({duration:30});held=null;await work;expect(p.transition?.at).toBeCloseTo(104.12)
})
