import {it,expect,vi,afterEach,beforeEach} from 'vitest'
import {AudioCache} from '../realtime/cache'
import {BridgePlayer} from './transport'
import type {BridgeCase} from './types'
class Param{value=0;events:any[]=[];setValueAtTime(v:number,t:number){this.events.push(['set',v,t])}linearRampToValueAtTime(v:number,t:number){this.events.push(['ramp',v,t])}cancelScheduledValues(){}setTargetAtTime(){}}
class Node{gain=new Param();frequency=new Param();Q=new Param();type='';buffer:any;starts:number[]=[];stops=0;onended:any;connect(){}disconnect(){}start(t:number){this.starts.push(t)}stop(){this.stops++}}
class Context{static all:Context[]=[];sources:Node[]=[];currentTime=0;sampleRate=44100;state='running';destination=new Node();audioWorklet={addModule:async()=>{}};constructor(){Context.all.push(this)}createGain(){return new Node()}createBufferSource(){const n=new Node();this.sources.push(n);return n}createBiquadFilter(){return new Node()}async resume(){this.state='running'}async suspend(){this.state='suspended'}async close(){this.state='closed'}}
class Worklet extends Node{port={postMessage:vi.fn(),onmessage:null}}
const c={id:'test',start:50,end:58,duration:8,rate:1,bEntry:0,bEnd:8,bVoiceStart:9,aVoiceEnd:57,bars:4,pre:4,post:10,restore:11,assets:Object.fromEntries(['aMaster','aVocal','bMaster','bVocal'].map(k=>[k,{url:k,sha256:k,bytes:1,duration:k.startsWith('a')?12:18}])),eq:{a:[{t:0,low:-9,mid:0,high:-1.4},{t:8,low:-9,mid:0,high:-1.4}],b:[{t:0,low:-7,mid:0,high:1.2},{t:8,low:-7,mid:0,high:1.2}]}} as unknown as BridgeCase
let players:BridgePlayer[]=[]
const make=()=>{const p=new BridgePlayer(new URL('https://test.example/'),()=>{});players.push(p);return p}
beforeEach(()=>{Context.all=[];vi.stubGlobal('AudioContext',Context);vi.stubGlobal('AudioWorkletNode',Worklet);vi.stubGlobal('requestAnimationFrame',vi.fn(()=>1));vi.stubGlobal('cancelAnimationFrame',vi.fn());vi.spyOn(AudioCache.prototype,'load').mockImplementation(async asset=>({duration:asset.duration} as AudioBuffer))})
afterEach(()=>{players.forEach(p=>p.dispose());players=[];vi.restoreAllMocks();vi.unstubAllGlobals()})
it('all stems share one clock, pause preserves scheduling and restart stops every old source',async()=>{
 const p=make();await p.play(c,'bridge');const ctx=Context.all[0];expect(ctx.sources.map(n=>n.starts[0])).toEqual([.1,.1,4.1,4.1]);expect(p.state.status).toBe('playing')
 await p.pause();expect(ctx.state).toBe('suspended');expect(p.state.status).toBe('paused');await p.resume();expect(p.state.status).toBe('playing');expect(ctx.sources).toHaveLength(4)
 await p.play(c,'reference');expect(ctx.sources.slice(0,4).every(n=>n.stops===1)).toBe(true);expect(ctx.sources.slice(4).map(n=>n.starts[0])).toEqual([.1,4.1])
})
it('stop during decoding never starts stale sources even if the loader ignores abort',async()=>{
 const resolves:((b:AudioBuffer)=>void)[]=[];vi.mocked(AudioCache.prototype.load).mockImplementation(()=>new Promise(resolve=>resolves.push(resolve)))
 const p=make(),pending=p.play(c,'bridge');await vi.waitFor(()=>expect(resolves).toHaveLength(4));p.stop();resolves.forEach(r=>r({} as AudioBuffer));await pending;expect(Context.all[0].sources).toHaveLength(0);expect(p.state.status).toBe('idle')
})
it('replacing a still loading case keeps only the latest selection audible',async()=>{
 const resolves:((b:AudioBuffer)=>void)[]=[];vi.mocked(AudioCache.prototype.load).mockImplementation(()=>new Promise(resolve=>resolves.push(resolve)))
 const p=make(),old=p.play(c,'bridge');await vi.waitFor(()=>expect(resolves).toHaveLength(4));const next=p.play({...c,id:'next'},'reference');await vi.waitFor(()=>expect(resolves).toHaveLength(8));resolves.forEach(r=>r({} as AudioBuffer));await Promise.all([old,next]);expect(Context.all[0].sources).toHaveLength(2);expect(p.state.caseId).toBe('next')
})
