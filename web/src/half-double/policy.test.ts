import {expect,it} from 'vitest'
import {entryKeys,validateMetric} from './policy'
it('changes only the two B entry layers and never the source schedule',()=>{
 expect(entryKeys('natural')).toEqual({master:'bEntryMaster',vocal:'bEntryVocal'});expect(entryKeys('relay')).toEqual({master:'bAlignedMaster',vocal:'bAlignedVocal'})
})
it('requires a nonidentity endpoint-preserving 2:1 or 1:2 observed map',()=>{
 const c={bpm:[70,140],pre:4,post:8,plan:{start:10,end:18,duration:8,rate:1,window:{start:20,end:28}},metric:{relation:2,input:Array.from({length:17},(_,i)=>i*.5),output:Array.from({length:17},(_,i)=>i*.5+.04*Math.sin(Math.PI*i/16)),aBars:2,bBars:4,voicePolicy:'original-linear-fades'}}
 expect(()=>validateMetric(c)).not.toThrow()
 for(const bad of [{...c,bpm:[100,140]},{...c,metric:{...c.metric,output:c.metric.input}},{...c,metric:{...c.metric,output:c.metric.output.map((v,i)=>i===16?v+.1:v)}},{...c,plan:{...c.plan,rate:2}}])expect(()=>validateMetric(bad)).toThrow()
})
