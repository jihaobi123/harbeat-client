import {expect,it} from 'vitest'
import {qualityTrack as track} from './qualityFixture'
import {planAutomaticQuality} from './qualityPlan'
import {buildV30Eq} from '../v30/eq'
import {alignedVocalOverlap} from '../vocal-overlap/score'
const plan=(a=track('a'),tracks=[track('b')],position=0,ready=new Set<string>())=>planAutomaticQuality(a,tracks,position,{kind:'next'},ready,false)
it('compares multiple songs, entry points and full overlap lengths without waiting penalty',()=>{
 const a=track('a'),b=track('b'),c=track('c')
 b.windows.push({...b.windows[0],id:'later',start:12,end:16,bars:2,variants:{a:{...b.windows[0].variants.a,url:'later',sha256:'later',duration:4}}})
 const r=plan(a,[b,c]);expect(new Set(r.candidates.map(p=>p.to)).size).toBe(2)
 expect(new Set(r.candidates.filter(p=>p.to==='b').map(p=>p.window.id)).size).toBe(2)
 expect(r.candidates.every(p=>p.decision!.score.components.find(c=>c.key==='waiting')?.contribution===0)).toBe(true)
 expect(r.best!.end).toBe(78)
 expect(r.best!.v30Eq).toEqual(buildV30Eq(a,[b,c].find(t=>t.id===r.best!.to)!,r.best!))
})
it('keeps binding, weighted vocal overlap and full local beat checks',()=>{
 const a=track('a'),b=track('b');const r=plan(a,[b]);const p=r.best!
 const v=alignedVocalOverlap(a.vocals!,b.vocals!,{aStart:p.start,bStart:p.window.start,bEnd:p.window.end,duration:p.duration,rate:p.rate})
 expect(p.decision!.score.components.find(c=>c.key==='vocal')!.contribution).toBeCloseTo(-.3*v.weightedOverlap,12)
 b.alignment!.bars[0].beats[1]+=.12
 expect(plan(a,[b]).best).toBeNull()
 b.alignment!.bars[0].beats[1]-=.12;b.preprocessing!.bindingChecks.reportHash=false
 expect(plan(a,[b]).best).toBeNull()
})
it('respects exact song, preparation lead and minimum listening duration',()=>{
 const a=track('a'),b=track('b'),c=track('c')
 expect(planAutomaticQuality(a,[b,c],0,{kind:'next',targetId:'c'},new Set(),false).best!.to).toBe('c')
 expect(plan(a,[b],70).best).toBeNull()
 expect(plan(a,[b],68,new Set(['b','clip'])).best!.start).toBeGreaterThanOrEqual(68.25)
 a.alignment!.bars.forEach(bar=>{if(bar.start>=38)bar.valid=false})
 expect(plan(a,[b]).best).toBeNull()
})
it('rejects missing band evidence rather than awarding a neutral continuity score',()=>{
 const b=track('b');b.alignment!.bandFrames=[];expect(plan(track('a'),[b]).best).toBeNull()
})
