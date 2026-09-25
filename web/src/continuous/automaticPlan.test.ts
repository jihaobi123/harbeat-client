import {it,expect} from 'vitest'
import {planAutomatic} from './automaticPlan'
import {planNext,type Track} from '../realtime/planner'
function track(id:string):Track{
 return {id,title:id,bpm:120,style:'Trap',styleScore:1,duration:150,
  native:{url:id,sha256:id,bytes:1,duration:150},bars:Array.from({length:60},(_,i)=>i*2),
  sections:[{start:0,end:150,label:'verse'}],vocals:[],energy:[],
  windows:[{id:'w',start:0,end:8,bars:4,role:'intro',energy:0,variants:{a:{url:'entry',sha256:'entry',bytes:1,rate:1,duration:8}}}]}
}
it('finds a complete overlap before an unmetered tail where the old 22-second trigger finds none',()=>{
 const a=track('a'),b=track('b')
 expect(planNext(a,[a,b],128,{kind:'next',targetId:'b'},new Set(),18,false).best).toBeNull()
 const result=planAutomatic(planNext,a,[a,b],20,{kind:'next',targetId:'b'},new Set())
 expect(result.best).not.toBeNull();expect(result.best!.start).toBeGreaterThan(80)
 expect(result.best!.end).toBeLessThanOrEqual(118)
 expect(result.best!.duration).toBe(8)
})
it('widens backwards when the last region is ineligible, without accepting a past cue after seek',()=>{
 const a=track('a'),b=track('b')
 const planner:typeof planNext=(a,tracks,pos,intent,ready,budget,required)=>planNext(a,tracks,pos,intent,ready,budget,required,(_a,_b,c)=>c.end>80?'bad tail':null)
 const result=planAutomatic(planner,a,[a,b],20,{kind:'next',targetId:'b'},new Set())
 expect(result.best).not.toBeNull();expect(result.best!.end).toBeLessThanOrEqual(80)
 expect(planAutomatic(planner,a,[a,b],90,{kind:'next',targetId:'b'},new Set()).best).toBeNull()
})
