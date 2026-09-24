import {describe,it,expect,vi} from 'vitest'
import {nativeSegment,SegmentScheduler} from './segments'
import type {Track,Asset} from '../realtime/planner'
const asset=(id:string,duration:number):Asset=>({url:id,sha256:id,bytes:1,duration})
function track(){const native=asset('prefix',150);return {id:'a',duration:240,native,audioSegments:[{start:0,end:150,asset:native},{start:150,end:180,asset:asset('one',30)},{start:180,end:210,asset:asset('two',30)},{start:210,end:240,asset:asset('three',30)}]} as Track}
const buffer=(duration:number)=>({duration} as AudioBuffer)
async function settle(){for(let i=0;i<6;i++)await Promise.resolve()}
function setup(offset=140){let now=10;const calls:any[]=[],release=vi.fn(),load=vi.fn(async(a:Asset,_signal:AbortSignal)=>buffer(a.duration)),changed=vi.fn();const stream=new SegmentScheduler(track(),10,offset,{now:()=>now,load,schedule:(...args:any[])=>{calls.push(args);return release},changed});stream.begin(buffer(nativeSegment(track(),offset).asset.duration));return {stream,calls,load,release,changed,time:(x:number)=>{now=x}}}
describe('native segment timeline',()=>{
 it('maps late seeks to the containing source file and rejects discontinuous manifests',()=>{expect(nativeSegment(track(),181).asset.url).toBe('two');const bad=track();bad.audioSegments![1].start=150.1;expect(()=>nativeSegment(bad,181)).toThrow('连续');expect(nativeSegment({...track(),audioSegments:undefined},181).asset.url).toBe('prefix')})
 it('anchors the exact adjacent native starts to the same clock without per-segment fades',async()=>{const x=setup();await settle();expect(x.calls.map(c=>c.slice(1))).toEqual([[10,140,10,true],[20,0,30,false]]);expect(x.stream.pins).toEqual(new Set(['prefix','one']));expect(x.stream.deadline).toBe(50)})
 it('retires old nodes and bounds pins to the current and one upcoming segment',async()=>{const x=setup();await settle();x.time(21);x.stream.pump();await settle();expect(x.release).toHaveBeenCalledTimes(1);expect(x.stream.pins).toEqual(new Set(['one','two']));expect(x.calls[2].slice(1)).toEqual([50,0,30,false])})
 it('does not fetch later chunks until they are within thirty seconds',async()=>{const x=setup(0);await settle();expect(x.load).not.toHaveBeenCalled();expect(x.stream.pins).toEqual(new Set(['prefix']));x.time(130);x.stream.pump();await settle();expect(x.load).toHaveBeenCalledTimes(1)})
 it('keeps the covered endpoint while a fetch misses its deadline and refuses a late silent start',async()=>{const x=setup(0);let complete!:(b:AudioBuffer)=>void;x.load.mockImplementation(()=>new Promise(r=>complete=r));x.time(130);x.stream.pump();expect(x.stream.deadline).toBe(160);x.time(161);complete(buffer(30));await settle();expect(x.calls).toHaveLength(1);expect(x.stream.late).toBe(true);expect(x.stream.deadline).toBe(160)})
 it('aborts retired loading and never schedules stale completion',async()=>{const x=setup(0);let complete!:(b:AudioBuffer)=>void;x.load.mockImplementation(()=>new Promise(r=>complete=r));x.time(130);x.stream.pump();const signal=x.load.mock.calls[0][1];x.stream.dispose();expect(signal.aborted).toBe(true);complete(buffer(30));await settle();expect(x.calls).toHaveLength(1);expect(x.stream.pins.size).toBe(0)})
})

it('keeps a sub-sample seek before a boundary inside the preceding verified asset',()=>{expect(nativeSegment(track(),150-1/88200).asset.url).toBe('prefix')})
