import {afterEach,expect,it,vi} from 'vitest'
import {qualityTrack} from '../continuous/qualityFixture'
import {mixNearby} from './nearby'
const makeResult=(a:any,b:any,p:any)=>({schema:'harbeat.metric-mix-result.v1',id:p.id,status:'ready',plan:{from:a.id,to:b.id,start:p.start,end:p.end,duration:p.duration,rate:p.rate,bStart:p.window.start,bEnd:p.window.end,windowId:p.window.id},decision:{recommended:'original',methods:{original:{eligible:true}}},assets:{original:{url:'render/'+p.id}}}) as any
function setup(){
 const a=qualityTrack('a'),b=qualityTrack('b')
 const player:any={current:a,position:10,playing:true,transition:null,logs:[],cache:{ready:new Set(),load:vi.fn(async()=>({}))},arm:vi.fn(async()=>{}),start:vi.fn(),seek:vi.fn()}
 const prepare=vi.fn(async(p:any)=>makeResult(a,b,p)),controller=new AbortController()
 return {a,b,player,prepare,signal:controller.signal,controller}
}
afterEach(()=>vi.useRealTimers())
it('one live request prepares, preloads and arms a nearby cue without restarting A',async()=>{
 const s=setup();await mixNearby(s)
 expect(s.player.arm).toHaveBeenCalledTimes(1)
 const result=s.player.arm.mock.calls[0][0]
 expect(result.plan.start).toBeGreaterThan(10.5);expect(result.plan.start).toBeLessThan(35)
 expect(s.player.cache.load).toHaveBeenCalledTimes(2)
 expect(s.player.start).not.toHaveBeenCalled();expect(s.player.seek).not.toHaveBeenCalled()
})
it('replaces an expired prepared cue instead of replaying it or requiring another click',async()=>{
 const s=setup(),old=makeResult(s.a,s.b,{id:'old',start:2,end:10,duration:8,rate:1,window:s.b.windows[0]})
 await mixNearby({...s,ready:{result:old,method:'original'}})
 expect(s.prepare).toHaveBeenCalled();expect(s.player.arm).toHaveBeenCalledTimes(1)
 expect(s.player.arm.mock.calls[0][0].id).not.toBe('old')
})
it('reuses an already prepared nearby cue without a second cloud job',async()=>{
 const s=setup(),result=makeResult(s.a,s.b,{id:'ready',start:18,end:26,duration:8,rate:1,window:s.b.windows[0]})
 await mixNearby({...s,ready:{result,method:'original'}})
 expect(s.prepare).not.toHaveBeenCalled();expect(s.player.arm).toHaveBeenCalledWith(result,'original',s.b,expect.any(AbortSignal))
})
it('replans automatically when a slow cloud job misses its cue',async()=>{
 vi.useFakeTimers();const s=setup();let firstSignal:AbortSignal|undefined
 s.prepare.mockImplementationOnce(async(p:any,signal?:AbortSignal)=>{firstSignal=signal;s.player.position=p.start+1;return new Promise(()=>{})})
 const task=mixNearby(s);await vi.advanceTimersByTimeAsync(300);await task
 expect(firstSignal?.aborted).toBe(true);expect(s.prepare).toHaveBeenCalledTimes(2)
 expect(s.player.arm).toHaveBeenCalledTimes(1);expect(s.player.arm.mock.calls[0][0].plan.start).toBeGreaterThan(s.player.position+.5)
})
it('cancellation during a stalled preload prevents a late handoff',async()=>{
 const s=setup();let release!:()=>void;s.player.cache.load.mockImplementation(()=>new Promise(r=>release=()=>r({})))
 const task=mixNearby(s),rejected=expect(task).rejects.toMatchObject({name:'AbortError'})
 await vi.waitFor(()=>expect(s.player.cache.load).toHaveBeenCalledTimes(2));s.controller.abort();await rejected;release()
 expect(s.player.arm).not.toHaveBeenCalled();expect(s.player.start).not.toHaveBeenCalled()
})
it('rejects missing local beat evidence without submitting a cloud job or hard cutting',async()=>{
 const s=setup();s.b.alignment!.bars=[]
 await expect(mixNearby(s)).rejects.toThrow(/接点/)
 expect(s.prepare).not.toHaveBeenCalled();expect(s.player.arm).not.toHaveBeenCalled()
})

it('reserves measured cold preparation time while still using the nearby planner',async()=>{
 const s=setup();await mixNearby({...s,leadSeconds:40})
 expect(s.player.arm.mock.calls[0][0].plan.start).toBeGreaterThanOrEqual(50)
 expect(s.player.start).not.toHaveBeenCalled()
})
it('reuses a ready cue earlier than any new cold-prepared candidate',async()=>{
 const s=setup(),result=makeResult(s.a,s.b,{id:'ready-sooner',start:45,end:53,duration:8,rate:1,window:s.b.windows[0]})
 await mixNearby({...s,leadSeconds:40,ready:{result,method:'original'}})
 expect(s.prepare).not.toHaveBeenCalled();expect(s.player.arm.mock.calls[0][0].id).toBe('ready-sooner')
})
