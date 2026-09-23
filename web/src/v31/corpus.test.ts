import {describe,it,expect} from 'vitest'
import {readFileSync,writeFileSync} from 'node:fs'
import {join} from 'node:path'
import {planNext} from '../realtime/planner'
import {guardPlan,type GuardCatalog} from '../guarded/planner'
const dir=process.env.V31_CORPUS
const read=(name:string)=>JSON.parse(readFileSync(join(dir!,name),'utf8'))
describe.skipIf(!dir)('twenty-track real evidence and paired decisions',()=>{
 it('builds matched requests with all twenty outgoing songs and retains failures',()=>{
  const v3=read('v3-catalog.json') as GuardCatalog,g=read('auto-catalog.json') as GuardCatalog
  expect(v3.tracks).toHaveLength(20);expect(g.tracks).toHaveLength(20)
  expect(new Set(g.tracks.map(t=>t.provenance?.masterSha256)).size).toBe(20)
  const rows:any[]=[],bCount:Record<string,number>={},cases:any[]=[];let guardPass=0,v3Pass=0,both=0
  for(const a of g.tracks){
   const va=v3.tracks.find(t=>t.id===a.id)!
   expect(a.native.sha256).toBe(va.native.sha256);expect(a.preprocessing?.masterSha256).toBe(a.provenance?.masterSha256)
   for(const b of g.tracks){if(a.id===b.id)continue
    for(const pos of [0,15,30,45,60,75,90,105,120].filter(x=>x<a.duration-12)){
     const r=guardPlan(g,{},a,g.tracks,pos,{kind:'next',targetId:b.id},new Set(),a.duration-pos,false),old=planNext(va,v3.tracks,pos,{kind:'next',targetId:b.id},new Set(),18,false)
     if(r.best){guardPass++;const p:any=r.best,ev=g.evidence[b.id].windows[p.window.id]
      expect(p.end).toBeGreaterThanOrEqual(p.protection.exit.sectionEnd);expect(p.window.start).toBeGreaterThanOrEqual(ev.sectionStart);expect(p.window.end).toBeLessThanOrEqual(ev.sectionEnd)
      expect(b.vocals?.some(([lo,hi])=>hi>p.window.start&&lo<p.window.end+.1)).toBe(false)
      expect(p.midDuck).toBe(false);expect(p.gridError).toBeLessThanOrEqual(.065)
      expect(p.asset.duration).toBeCloseTo((p.window.end-p.window.start)/p.rate,3)
     }
     if(old.best)v3Pass++;if(old.best&&r.best)both++
     rows.push({id:`${a.id}:${b.id}:${pos}`,a:a.id,b:b.id,position:pos,v3:!!old.best,protected:!!r.best,waitV3:old.best?old.best.end-pos:null,waitProtected:r.best?r.best.end-pos:null,reason:!r.best?[...new Set(r.exclusions.map(x=>x.reason))].join('；'):null,exclusionCodes:[...new Set(r.exclusions.map(x=>x.code))]})
    }
   }
   const options=rows.filter(r=>r.a===a.id).sort((x,y)=>Number(y.v3&&y.protected)-Number(x.v3&&x.protected)||Number(y.protected)-Number(x.protected)||Number(y.v3)-Number(x.v3)||(bCount[x.b]||0)-(bCount[y.b]||0)||Math.abs(x.position-30)-Math.abs(y.position-30)||x.id.localeCompare(y.id))
   cases.push(options[0]);bCount[options[0].b]=(bCount[options[0].b]||0)+1
  }
  const useful=cases.filter(x=>x.v3&&x.protected),other=cases.filter(x=>!x.v3||!x.protected)
  const coverage={trackCount:20,requests:rows.length,v3Plans:v3Pass,protectedPlans:guardPass,pairedPlans:both,protectedUnavailable:rows.length-guardPass,distinctProtectedOutgoing:new Set(rows.filter(x=>x.protected).map(x=>x.a)).size,distinctProtectedIncoming:new Set(rows.filter(x=>x.protected).map(x=>x.b)).size,caseCount:cases.length,pairedCaseCount:useful.length,notes:'可执行数只代表通过约束，不代表听感更好；每一曲对使用相同请求位置，V3 18秒，保护版搜至试听素材结束。'}
  expect(cases).toHaveLength(20);expect(new Set(cases.map(x=>x.a)).size).toBe(20)
  writeFileSync(join(dir!,'cases.json'),JSON.stringify({cases:[...useful,...other],coverage},null,2));writeFileSync(join(dir!,'coverage-matrix.json'),JSON.stringify({coverage,rows},null,2));console.log(JSON.stringify(coverage))
 },120000)
})
