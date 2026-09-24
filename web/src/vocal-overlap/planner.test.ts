import {describe,expect,it} from 'vitest'
import {planNext,type Track} from '../realtime/planner'
import {planV31} from '../v31-release/release'
import {buildV30Eq} from '../v30/eq'
import {planVocalOverlap,type OverlapPlan} from './planner'

function track(id:string):Track {
  const t:Track = {id,title:id,bpm:120,style:'Trap',styleScore:1,duration:80,reportId:'report'+id,
    native:{url:id,sha256:'native-'+id,duration:80,bytes:1},
    provenance:{masterSha256:'m'+id,reportSha256:'r'+id,vocalSha256:'v'+id,runId:'run'+id},
    bars:Array.from({length:40},(_,i)=>i*2),sections:[{start:0,end:80,label:'verse'}],
    vocals:id==='a'?[[2.3,5.7]]:[[.3,3.7]],energy:[{start:0,end:80,value:.4}],
    windows:[{id:'w',start:0,end:8,bars:4,role:'intro',energy:.4,
      variants:{a:{url:'clip',sha256:'clip-sha',duration:8,bytes:1,rate:1}}}],
    alignment:{schema:'x',status:'candidate',source:{reportId:'report'+id,masterSha256:'m'+id,reportSha256:'r'+id,vocalSha256:'v'+id},
      bars:[],phrases:[],exits:[],conflicts:[],
      bandFrames:[{start:0,end:80,rmsDbfs:-15,low:-20,mid:-22,high:-30}],limitations:[]}}
  t.preprocessing={schema:'harbeat.preprocessing-evidence.v1',reportId:t.reportId!,reportSha256:'r'+id,masterSha256:'m'+id,reportSnapshotUrl:'report.json',bindingChecks:{reportHash:true,masterHash:true},sections:{items:[]},beatGrid:{bars_ms:[],beats_ms:[]},tempo:{},vocalActivity:{status:'ready',time_origin:'master_audio_start',unit:'ms',source:{track_id:id,analysis_run_id:'run'+id,vocal_sha256:'v'+id},intervals:t.vocals!.map(([s,e])=>({start_ms:s*1000,end_ms:e*1000}))},vocalRms:{points:[]},energy:{},genre:{},extensions:[]}
  return t
}
const input=(a:Track,b:Track,budget=18)=>[a,[a,b] as Track[],0,{kind:'next' as const,targetId:b.id},new Set<string>(),budget,false] as const

describe('controlled vocal-score experiment',()=>{
  it('moves an eligible A timing while keeping the full baseline entry material',()=>{
    const a=track('a'),b=track('b'),args=input(a,b)
    const baseline=planV31(...args).best!, result=planVocalOverlap(...args), p=result.best as OverlapPlan
    expect(baseline.end).toBe(10)
    expect(p.end).toBe(12)
    expect(p.start-baseline.start).toBe(2)
    expect(p.duration).toBe(baseline.duration)
    expect(p.window).toEqual(baseline.window)
    expect(p.asset).toEqual(baseline.asset)
    expect(p.rate).toBe(baseline.rate)
    expect(p.to).toBe(baseline.to)
    expect(p.end).toBeLessThanOrEqual(18)
    expect(p.automation).toBeUndefined()
    expect(p.phrase).toBeUndefined()
    expect(p.vocalOverlap.baselinePlanId).toBe(baseline.id)
    expect(p.vocalOverlap.shiftSec).toBe(2)
  })
  it('changes only the vocal term of each retained candidate and preserves all original eligibility',()=>{
    const a=track('a'),b=track('b'),args=input(a,b)
    b.windows.push({...b.windows[0],id:'another',start:10,end:18,variants:{a:{...b.windows[0].variants.a,url:'other',sha256:'other'}}})
    const original=planNext(...args), anchor=original.best!, result=planVocalOverlap(...args)
    for(const p of result.candidates as OverlapPlan[]) {
      const old=original.candidates.find(x=>x.id===p.id)!
      expect(old).toBeTruthy()
      expect(p.window.id).toBe(anchor.window.id)
      expect(p.asset.sha256).toBe(anchor.asset.sha256)
      expect(p.decision!.score.components.filter(x=>x.key!=='vocal')).toEqual(old.decision!.score.components.filter(x=>x.key!=='vocal'))
      expect(p.score).toBeCloseTo(old.score+.3*old.aVocal*old.bVocal-.3*p.vocalOverlap.weightedOverlap,12)
      expect(p.decision!.score.components.reduce((n,c)=>n+c.contribution,0)).toBeCloseTo(p.score,12)
      expect(p.midDuck).toBe(old.midDuck)
      expect(p.duration).toBe(anchor.duration)
    }
    expect(result.candidates.length).toBeLessThan(original.candidates.length)
  })
  it('uses the existing dynamic EQ for the newly selected source range',()=>{
    const a=track('a'),b=track('b'),p=planVocalOverlap(...input(a,b)).best!
    expect(p.v30Eq).toEqual(buildV30Eq(a,b,p))
    expect(p.v30Eq!.limits).toEqual({lowHighDb:3,midDb:2,slewDbPerSec:3})
  })
  it('leaves the formal release result and input tracks unchanged',()=>{
    const a=track('a'),b=track('b'),args=input(a,b),snapshot=JSON.stringify([a,b]),before=planV31(...args)
    planVocalOverlap(...args)
    expect(JSON.stringify([a,b])).toBe(snapshot)
    expect(planV31(...args)).toEqual(before)
  })
  it('preserves baseline no-plan, ready-state and budget constraints',()=>{
    const a=track('a'),b=track('b')
    expect(planVocalOverlap(...input(a,b,8)).best).toBeNull()
    expect(planVocalOverlap(a,[a,b],0,{kind:'next',targetId:b.id},new Set(),18,true).best).toBeNull()
    const prepared=new Set([b.native.url,b.windows[0].variants.a.url])
    expect(planVocalOverlap(a,[a,b],0,{kind:'next',targetId:b.id},prepared,18,true).best).not.toBeNull()
  })
  it('reports unavailable source or EQ evidence without silently falling back',()=>{
    const a=track('a'),b=track('b');b.alignment!.source.vocalSha256='wrong'
    expect(planVocalOverlap(...input(a,b)).best).toBeNull()
    b.alignment!.source.vocalSha256='vb';b.alignment!.bandFrames=[]
    expect(planVocalOverlap(...input(a,b)).best).toBeNull()
    b.alignment!.bandFrames=[{start:0,end:80,rmsDbfs:-15,low:-20,mid:-22,high:-30}];b.vocals=[[4,2]]
    const invalid=planVocalOverlap(...input(a,b))
    expect(invalid.best).toBeNull()
    expect(invalid.exclusions.some(e=>e.code==='vocal_overlap_unavailable')).toBe(true)
  })
  it.each(['changed-row','reordered-rows','failed-binding','time-origin','report-id','vocal-source'])('rejects mismatched runtime VAD evidence: %s',kind=>{
    const a=track('a'),b=track('b')
    if(kind==='changed-row')b.vocals![0][0]+=.1
    if(kind==='reordered-rows'){b.vocals!.push([10,11]);b.preprocessing!.vocalActivity.intervals.push({start_ms:10000,end_ms:11000});b.vocals!.reverse()}
    if(kind==='failed-binding')b.preprocessing!.bindingChecks.reportHash=false
    if(kind==='time-origin')b.preprocessing!.vocalActivity.time_origin='stem_start'
    if(kind==='report-id')b.preprocessing!.reportId='another'
    if(kind==='vocal-source')(b.preprocessing!.vocalActivity.source as {vocal_sha256:string}).vocal_sha256='another'
    const result=planVocalOverlap(...input(a,b))
    expect(result.best).toBeNull()
    expect(result.exclusions.some(e=>e.code==='vocal_overlap_unavailable')).toBe(true)
  })
  it.each([[null],{}])('returns unavailable for malformed runtime VAD shapes',malformed=>{
    const a=track('a'),b=track('b');b.vocals=malformed as any
    const result=planVocalOverlap(...input(a,b))
    expect(result.best).toBeNull()
    expect(result.exclusions.some(e=>e.code==='vocal_overlap_unavailable')).toBe(true)
  })
})
