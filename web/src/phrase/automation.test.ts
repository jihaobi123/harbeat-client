import {describe,it,expect} from 'vitest'
import {buildAutomation,gainAt} from './automation'
import type {Plan,Track} from '../realtime/planner'
const track=(level=-20)=>({alignment:{source:{masterSha256:'m'},bandFrames:[{start:0,end:120,rmsDbfs:level,low:level,mid:level,high:level}]},provenance:{masterSha256:'m'}} as unknown as Track)
const plan=()=>({start:10,end:14,duration:4,rate:1,window:{start:20,end:24},phrase:{fadeStart:12,exit:{tailEnd:12}}} as Plan)
describe('phrase gain and measured EQ',()=>{
 it('holds outgoing gain and dry EQ through the protected tail, then fades to zero',()=>{const p=plan(),r=buildAutomation(track(),track(),p,'fixed');expect(gainAt(r.aGain,1.9)).toBe(1);expect(gainAt(r.aGain,3)).toBe(.5);expect(gainAt(r.aGain,4)).toBe(0);expect(r.aEq.filter(x=>x.t<=2).every(x=>x.low===0&&x.mid===0&&x.high===0)).toBe(true)})
 it('changes EQ with measured spectral balance while keeping identical gain and point choices',()=>{const p=plan(),quiet=buildAutomation(track(),track(-45),p,'adaptive'),loud=buildAutomation(track(),track(-20),p,'adaptive');expect(quiet.aGain).toEqual(loud.aGain);expect(quiet.bEq).not.toEqual(loud.bEq);for(const q of loud.bEq){expect(q.low).toBeGreaterThanOrEqual(-9);expect(q.low).toBeLessThanOrEqual(0);expect(q.mid).toBeGreaterThanOrEqual(-4);expect(q.high).toBeGreaterThanOrEqual(-3)}expect(loud.bEq.at(-1)).toEqual({t:4,low:0,mid:0,high:0})})
 it('rejects missing and stale energy instead of inventing values',()=>{const p=plan(),a=track(),b=track();b.alignment!.source.masterSha256='wrong';expect(()=>buildAutomation(a,b,p,'adaptive')).toThrow();b.alignment!.source.masterSha256='m';b.alignment!.bandFrames=[];expect(()=>buildAutomation(a,b,p,'adaptive')).toThrow()})
})
