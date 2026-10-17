import {afterEach,expect,it,vi} from 'vitest'
import {LiveTransport} from '../realtime/transport'
import {qualityTrack} from '../continuous/qualityFixture'
import type {Plan,Track} from '../realtime/planner'
class Param{value=0;setValueAtTime(){}linearRampToValueAtTime(){}cancelAndHoldAtTime(){}cancelScheduledValues(){}setTargetAtTime(){}}
class Node{gain=new Param();frequency=new Param();Q=new Param();buffer:any;starts:any[]=[];connect(){}disconnect(){}start(...args:any[]){this.starts.push(args)}stop(){}}
class Context{currentTime=0;sampleRate=44100;state='running';destination=new Node();audioWorklet={addModule:async()=>{}};createGain(){return new Node()}createBufferSource(){return new Node()}createBiquadFilter(){return new Node()}async resume(){}async close(){}}
class Worklet extends Node{port={postMessage:vi.fn(),onmessage:null}}
let player:LiveTransport|undefined
afterEach(()=>{player?.dispose();vi.useRealTimers();vi.unstubAllGlobals()})
function track(id:string):Track{const t=qualityTrack(id);t.duration=220;t.native={url:id+'-first',sha256:id+'-first',duration:150,bytes:1};t.audioSegments=[{start:0,end:150,asset:t.native},{start:150,end:220,asset:{url:id+'-last',sha256:id+'-last',duration:70,bytes:1}}];return t}
it.each([{start:164,bEnd:159.8,from:'a-last',fromOffset:10,to:'b-last',toOffset:9.8,required:['a-last','b-last']},{start:152,bEnd:148,from:'a-first',fromOffset:148,to:'b-first',toOffset:148,required:['a-first','a-last','b-first','b-last']}])('replays a frozen transition at $start after preloading all crossed chunks',async example=>{
 vi.useFakeTimers();vi.stubGlobal('window',{setInterval,clearInterval});vi.stubGlobal('AudioContext',Context);vi.stubGlobal('AudioWorkletNode',Worklet)
 const a=track('a'),b=track('b'),p={id:'frozen',from:'a',to:'b',start:example.start,end:example.start+4.8,duration:4.8,restore:167,rate:1,score:1,midDuck:false,aVocal:0,bVocal:0,aEnergy:.4,bEnergy:.4,gridError:0,reason:'test',section:'verse',prepared:false,
  asset:{url:'entry',sha256:'entry',duration:4.8,bytes:1},window:{id:'entry',start:example.bEnd-4.8,end:example.bEnd,bars:2,role:'verse',energy:.4,variants:{}}} as Plan
 player=new LiveTransport([a,b],()=>{},new URL('https://example.test/'),{autoNext:false,prewarm:false});await player.initialize()
 const loaded:string[]=[]
 player.cache.load=vi.fn(async asset=>{loaded.push(asset.url);const buffer={label:asset.url,duration:asset.duration,length:asset.duration*44100,numberOfChannels:2} as unknown as AudioBuffer;player!.cache.buffers.set(asset.url,buffer);return buffer})
 await player.playComparison(p,0,{experimentId:'test',arm:'variant',midDb:-5,skipWaiting:true})
 for(const url of example.required)expect(loaded).toContain(url)
 expect((player.active!.sources[0] as any).buffer.label).toBe(example.from)
 expect((player.active!.sources[0] as any).starts[0][1]).toBe(example.fromOffset)
 expect((player.pending!.deck.sources[1] as any).buffer.label).toBe(example.to)
 expect((player.pending!.deck.sources[1] as any).starts[0][1]).toBeCloseTo(example.toOffset)
 expect(player.pending!.plan).toBe(p)
})
