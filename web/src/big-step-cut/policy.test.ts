import {expect,it} from 'vitest'
import {cutCurves,validateBoundary} from './policy'
import {valueAt} from '../melody-overlap/policy'
const example=()=>({pre:4,post:8,bpm:[98,136],cutEdgeSeconds:.005,plan:{start:120,end:123.55,duration:3.55,rate:1,window:{start:0,end:3.55,bars:2}},boundary:{aSection:{start:100,end:120.005},bSection:{start:0,end:14},aDownbeat:120,aObservedBar:{start:119.99,end:122.44,beats:[119.99,120.6,121.21,121.83],valid:true},bDownbeat:0,bBars:[{start:0,end:1.77,beats:[0,.44,.88,1.33],valid:true},{start:1.77,end:3.55,beats:[1.77,2.21,2.66,3.1],valid:true}],aProtected:[],bProtected:[],voicePolicy:'original-linear-fades',sectionTruth:'model-candidate'}})
it('exchanges accompaniment at the beginning while preserving exact original voice gains',()=>{
 const n=cutCurves(4,3.55,.005,'natural'),s=cutCurves(4,3.55,.005,'relay')
 expect(valueAt(s.a.master,4)).toBe(0);expect(valueAt(s.b.master,4.005)).toBe(1)
 for(const side of ['a','b'] as const){expect(s[side].voice).toEqual(n[side].voice);for(let t=0;t<8;t+=.013){expect(valueAt(s[side].master,t)+valueAt(s[side].correction,t)).toBeCloseTo(valueAt(n[side].voice,t),12)}}
 expect(valueAt(s.a.master,3.99)).toBe(1);expect(valueAt(s.b.master,3.99)).toBe(0)
})
it('rejects non-distant and near double/half pairs without changing native source speed',()=>{
 const c=example();expect(()=>validateBoundary(c)).not.toThrow();for(const bpm of [[98,100],[70,140],[140,70],[0,140],[98,NaN]])expect(()=>validateBoundary({...c,bpm})).toThrow();expect(()=>validateBoundary({...c,plan:{...c.plan,rate:1.1}})).toThrow()
})
it('requires nearby model boundaries, actual complete downbeat bars and fixed native cues',()=>{
 const c=example();for(const boundary of [{...c.boundary,aSection:{start:100,end:119}},{...c.boundary,bSection:{start:1,end:14}},{...c.boundary,bBars:[{...c.boundary.bBars[0],valid:false},c.boundary.bBars[1]]},{...c.boundary,bDownbeat:.1},{...c.boundary,bBars:[{...c.boundary.bBars[0],beats:[0,.44,.88]},c.boundary.bBars[1]]}])expect(()=>validateBoundary({...c,boundary})).toThrow()
 expect(()=>validateBoundary({...c,plan:{...c.plan,window:{...c.plan.window,end:3.6}}})).toThrow()
})
it('protects A through the complete reference overlap and rejects B mid-phrase',()=>{
 const c=example();for(const aProtected of [[[119.69,119.8]],[[123.56,124]]])expect(()=>validateBoundary({...c,boundary:{...c.boundary,aProtected}})).toThrow()
 expect(()=>validateBoundary({...c,boundary:{...c.boundary,bProtected:[[-.2,.5]]}})).toThrow();expect(()=>validateBoundary({...c,boundary:{...c.boundary,bProtected:[[0,1]]}})).not.toThrow()
})
it('binds A raw anchor to nearby valid observed bar evidence without moving its cue',()=>{
 const c=example();expect(()=>validateBoundary({...c,boundary:{...c.boundary,aObservedBar:undefined}})).toThrow();expect(()=>validateBoundary({...c,boundary:{...c.boundary,aObservedBar:{...c.boundary.aObservedBar,start:119.8,beats:[119.8,120.4,121,121.6]}}})).toThrow();expect(()=>validateBoundary({...c,boundary:{...c.boundary,aObservedBar:{...c.boundary.aObservedBar,valid:false}}})).toThrow()
})
