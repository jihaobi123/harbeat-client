import {describe,it,expect} from 'vitest'
import {planNext,vocalPresence,RequestGate,Track} from './planner'
const asset={url:'native.wav',sha256:'a',duration:120,bytes:1}
function track(id:string,style='Trap',energy=.5):Track{const t:Track={id,title:id,bpm:100,style,styleScore:.4,duration:120,native:asset,bars:Array.from({length:50},(_,i)=>i*2.4),sections:[{start:0,end:120,label:'verse'}],vocals:[],energy:[{start:0,end:120,value:energy}],windows:[{id:id+'w',start:0,end:9.6,bars:4,role:'verse',energy,variants:{a:{...asset,duration:9.6,rate:1}}},{id:id+'short',start:0,end:4.8,bars:2,role:'verse',energy,variants:{a:{...asset,duration:4.8,rate:1}}}]};t.provenance={masterSha256:id};t.mixProfile={schema:'harbeat.mix_profiles.v1',policy:{calibrationId:'master-rms-common-digital-full-scale-v1',energyUnit:'dBFS_RMS'},source:{masterSha256:id},energyCurve:[],energyFrames:[{start:0,end:120,dbfs:-18+energy*6,coverage:1,status:'measured'}],sections:[],windows:t.windows.map(w=>({id:w.id,entry:{start:w.start,end:w.end,style:{status:'needs_review',top:[],reasons:[]}},takeover:{start:w.end,end:w.end+16,style:{status:'model_candidate',top:[{style,score:.4}],reasons:[]}},sustain:[]}))};return t}
describe('rolling V3 planner',()=>{
 it('never selects a transition whose start is already missed',()=>{const p=planNext(track('a'),[track('b')],50,{kind:'next'},new Set(['native.wav']),10).best!;expect(p.start).toBeGreaterThan(50+.2);expect(p.end).toBeLessThanOrEqual(60);expect(p.end-p.start).toBeCloseTo(p.duration)})
 it('requires both prepared assets and a remaining body',()=>{expect(planNext(track('a'),[track('b')],50,{kind:'next'},new Set(),18).best).toBeNull();const b=track('b');b.duration=10;expect(planNext(track('a'),[b],50,{kind:'next'},new Set(['native.wav']),18).best).toBeNull()})
 it('respects requested song and style rather than silently replacing',()=>{expect(planNext(track('a'),[track('b')],10,{kind:'style',style:'Grime'},new Set(['native.wav']),18).best).toBeNull();expect(planNext(track('a'),[track('b')],10,{kind:'next',targetId:'c'},new Set(['native.wav']),18).best).toBeNull()})
 it('enforces requested energy direction',()=>{expect(planNext(track('a','Trap',.8),[track('b','Trap',.2)],10,{kind:'up'},new Set(['native.wav']),18).best).toBeNull();expect(planNext(track('a','Trap',.2),[track('b','Trap',.8)],10,{kind:'up'},new Set(['native.wav']),18).best).not.toBeNull()})
 it('keeps original V3 both-window vocal detection with merged padding',()=>{expect(vocalPresence([[1,2],[1.5,2.2]],0,10)).toBeCloseTo(1.8/10);const a=track('a');const b=track('b');a.vocals=[[0,120]];b.vocals=[[0,120]];expect(planNext(a,[b],10,{kind:'next'},new Set(['native.wav']),18).best?.midDuck).toBe(true)})
 it('rejects unknown voice information and absent or unreliable grids',()=>{const a=track('a');a.vocals=null;expect(planNext(a,[track('b')],10,{kind:'next'},new Set(['native.wav']),18).best).toBeNull();a.vocals=[];a.bars=[];expect(planNext(a,[track('b')],10,{kind:'next'},new Set(['native.wav']),18).best).toBeNull()})
 it('invalidates stale loads and defers requests after lock',()=>{const g=new RequestGate();const x=g.replace({kind:'next'});const y=g.replace({kind:'up'});expect(g.isCurrent(x)).toBe(false);expect(g.isCurrent(y)).toBe(true);g.locked=true;expect(g.replace({kind:'down'})).toBeNull();expect(g.deferred?.kind).toBe('down');g.reset();expect(g.isCurrent(y)).toBe(false)})
})

describe('decision evidence',()=>{
 it('records exact cue evidence and additive score components without changing selection',()=>{
  const a=track('a'),b=track('b');const result=planNext(a,[b],50,{kind:'next'},new Set(['native.wav']),10)
  const p=result.best!;const detail=(p as any).decision
  expect(detail).toBeDefined()
  expect(detail.cues.aExit.sourceSec).toBe(p.end)
  expect(detail.cues.aExit.rawBarIndex).toBe(a.bars.indexOf(p.end))
  expect(detail.cues.bEntry.sourceSec).toBe(p.window.start)
  expect(detail.score.components.reduce((v:number,x:any)=>v+x.contribution,0)).toBeCloseTo(p.score,12)
  expect(detail.strategy.alternativesEvaluated).toEqual([])
  expect(detail.strategy.midDuck.enabled).toBe(false)
 })
 it('explains exact filtering reasons even if no candidate exists',()=>{
  const result=planNext(track('a'),[track('b','Trap'),track('c','Grime')],50,{kind:'style',style:'Grime'},new Set(),10)
  const local=planNext(track('a'),[track('b','Trap')],50,{kind:'style',style:'Grime'},new Set(['native.wav']),10)
  expect(local.exclusions.some(x=>x.code==='local_style_mismatch'&&x.trackId==='b')).toBe(true)
  expect((result as any).exclusions.some((x:any)=>x.code==='asset_not_ready'&&x.trackId==='c')).toBe(true)
 })
})

it('applies an optional timing eligibility gate before choosing the entry material, preserving scores of eligible plans',()=>{
 const a=track('a'),b=track('b'),args=[a,[b] as Track[],50,{kind:'next'},new Set(['native.wav']),18,true] as const
 const before=planNext(...args)
 const gate=(_a:Track,_b:Track,cue:{window:{bars:number}})=>cue.window.bars===2?null:'local beats do not align'
 const after=planNext(...args,gate)
 expect(after.candidates.every((p:any)=>p.window.bars===2)).toBe(true)
 expect(after.exclusions.some((e:any)=>e.code==='local_beat_alignment')).toBe(true)
 for(const p of after.candidates)expect(p.score).toBe(before.candidates.find(q=>q.id===p.id)!.score)
 const blocked=planNext(...args,()=> 'invalid local grid')
 expect(blocked.best).toBeNull()
})
