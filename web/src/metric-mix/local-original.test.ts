import {expect,it} from 'vitest'
import {qualityTrack} from '../continuous/qualityFixture'
import {nearbyPlan} from './nearby'
import {originalInputs} from './local-original'
it('binds the nearest original mix to the verified sources and exact source ranges',()=>{
 const a=qualityTrack('a'),b=qualityTrack('b'),plan=nearbyPlan(a,b,10)!
 const inputs=originalInputs(a,b,plan)
 expect(inputs.outgoing[0].start).toBeLessThanOrEqual(plan.start)
 expect(inputs.outgoing.at(-1)!.end).toBeGreaterThanOrEqual(plan.end)
 expect(inputs.entry).toBe(plan.asset);expect(inputs.beatErrorMs).toBeLessThanOrEqual(65)
 for(const bad of [{...plan,from:'another'},{...plan,v30Eq:undefined}])expect(()=>originalInputs(a,b,bad)).toThrow()
 b.preprocessing!.masterSha256='unbound';expect(()=>originalInputs(a,b,plan)).toThrow()
})
it('includes both native body fragments when the eight-ms tail crosses a chunk boundary',()=>{
 const a=qualityTrack('a'),b=qualityTrack('b'),plan=nearbyPlan(a,b,10)!,end=plan.window.end+.004
 b.audioSegments=[{start:0,end,asset:{...b.native,duration:end}},{start:end,end:b.duration,asset:{...b.native,url:'b-tail',duration:b.duration-end}}]
 expect(originalInputs(a,b,plan).nativeTail).toHaveLength(2)
})
