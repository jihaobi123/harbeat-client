import {afterEach,expect,it,vi} from 'vitest'
vi.mock('./render',()=>({renderTail:vi.fn(async()=>({buffer:{length:308700,duration:7,numberOfChannels:2},receipt:{excerptPcmSha256:'rendered',window:{takeoverFrame:176400}}}))}))
import {renderTail} from './render'
import {MelodyYieldPlayer,type MelodyYieldCase,type State} from './transport'
class Param{value=0;points:any[]=[];setValueAtTime(...x:any[]){this.points.push(x)}linearRampToValueAtTime(...x:any[]){this.points.push(x)}cancelScheduledValues(){}setTargetAtTime(){}}
class Node{gain=new Param();frequency=new Param();Q=new Param();buffer:any;onended:any;type='';targets:Node[]=[];connect(n:Node){this.targets.push(n)}disconnect(){}start(...args:any[]){started.push({args,node:this})}stop(){stopped.push(this)}}
const started:{args:any[];node:Node}[]=[],stopped:Node[]=[],filters:Node[]=[]
class Context{currentTime=0;sampleRate=44100;state='running';destination=new Node();audioWorklet={addModule:async()=>{}};createGain(){return new Node()}createBiquadFilter(){const n=new Node();filters.push(n);return n}createBufferSource(){return new Node()}async resume(){}async close(){}}
const worklets:Worklet[]=[]
class Worklet extends Node{port:{postMessage:ReturnType<typeof vi.fn>;onmessage:null|((e:{data:any})=>void)}={postMessage:vi.fn(),onmessage:null};constructor(){super();worklets.push(this)}}
let player:MelodyYieldPlayer|undefined
afterEach(()=>{player?.dispose();started.length=0;stopped.length=0;filters.length=0;worklets.length=0;vi.useRealTimers();vi.unstubAllGlobals()})
function example():MelodyYieldCase{
 const keys=['aMaster','aOther','bEntryMaster','bEntryOther','bBodyMaster','bBodyOther']
 const assets=Object.fromEntries(keys.map(key=>[key,{url:key,sha256:key,duration:key.startsWith('a')?12:8,bytes:1}]))
 return {id:'case',aTitle:'a',bTitle:'b',pre:4,post:8,yieldEnd:2,firstBar:{},bpm:[120,120],planSha256:'frozen',assets,features:{},sourceVerification:{},plan:{id:'plan',start:10,end:18,duration:8,rate:1,window:{start:20,end:28},v30Eq:{a:[{t:0,low:-9,mid:0,high:-1.4}],b:[{t:0,low:-7,mid:0,high:1.2}]}}} as unknown as MelodyYieldCase
}
async function setup(change:(s:State)=>void=()=>{}){vi.useFakeTimers();vi.stubGlobal('window',{setInterval,clearInterval});vi.stubGlobal('AudioContext',Context);vi.stubGlobal('AudioWorkletNode',Worklet);player=new MelodyYieldPlayer(new URL('https://example.test/'),change);await player.initialize();player.cache!.load=vi.fn(async asset=>({key:asset.url,duration:asset.duration,length:asset.duration*44100,numberOfChannels:2} as unknown as AudioBuffer));return player}
function onsetEvent(){const message=worklets.at(-1)!.port.postMessage.mock.calls.filter(([m])=>m.kind==='arm').at(-1)![0];return {...message.events.find((e:any)=>e.name==='试听开始'),observedFrame:4480,quantumStart:4352,quantumFrames:128,late:0}}
function observe(data:any){worklets.at(-1)!.port.onmessage!({data})}
it('plays only the seven second rendered buffer and preserves full original-plan receipt',async()=>{
 const p=await setup(),c=example();await p.play(c,'relay',{roundId:'formal',letter:'A'});expect(renderTail).toHaveBeenCalled();expect(started).toHaveLength(1);const log=p.logs.find(x=>x.kind==='melody_started');expect(log).toMatchObject({roundId:'formal',letter:'A',plan:c.plan,total:7,nativeHandoffContext:4.1,renderReceipt:{excerptPcmSha256:'rendered'}});observe(onsetEvent());(p.ctx as unknown as Context).currentTime=7.2;vi.advanceTimersByTime(240);expect(p.logs.filter(x=>x.kind==='melody_finished')).toHaveLength(1)
})
it('does not start obsolete audio when stopped during offline rendering',async()=>{
 const p=await setup();let done!:(value:any)=>void;vi.mocked(renderTail).mockImplementationOnce(()=>new Promise(r=>done=r));const playing=p.play(example(),'natural');for(let i=0;i<10&&!done;i++)await Promise.resolve();p.stop();done({buffer:{},receipt:{}});await playing;expect(started).toHaveLength(0);expect(p.logs.some(x=>x.kind==='melody_finished')).toBe(false)
})
it('exports render failures rather than marking a review heard',async()=>{
 const p=await setup();vi.mocked(renderTail).mockRejectedValueOnce(Error('render failed'));await p.play(example(),'natural');expect(p.state.status).toBe('error');expect(p.logs.find(x=>x.kind==='melody_failed').message).toBe('render failed');expect(started).toHaveLength(0)
})
