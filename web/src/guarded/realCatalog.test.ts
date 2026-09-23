import {it,expect} from 'vitest'
import {readFileSync} from 'node:fs'
import {guardPlan,type GuardCatalog,type Reviews} from './planner'
it.skipIf(!process.env.GUARD_CATALOG)('validates real catalog geometry and blocks every unreviewed pair; in-memory test approvals exercise feasible branches',()=>{
 const c=JSON.parse(readFileSync(process.env.GUARD_CATALOG!,'utf8')) as GuardCatalog;let windows=0,assets=0,feasible=0,blocked=0
 for(const a of c.tracks){expect(a.bars.every((v,i)=>!i||v>a.bars[i-1])).toBe(true);for(const w of a.windows){windows++;const ev=c.evidence[a.id].windows[w.id];expect(w.start).toBeGreaterThanOrEqual(ev.sectionStart);expect(w.end).toBeLessThanOrEqual(ev.sectionEnd+.001);expect(ev.sourceHashes).toHaveLength(3);for(const v of Object.values(w.variants)){assets++;expect(Math.abs((w.end-w.start)/v.rate-v.duration)).toBeLessThan(.001);expect(v.sha256).toMatch(/^[a-f0-9]{64}$/)}}
  for(const b of c.tracks.filter(t=>t.id!==a.id)){expect(guardPlan(c,{},a,c.tracks,0,{kind:'next',targetId:b.id},new Set(),a.duration,false).best).toBeNull();blocked++
   // Synthetic approvals exist only in this test process: not human truth, never serialized to the release.
   const r:Reviews={exits:{},entries:{}};for(const x of c.evidence[a.id].exits)r.exits![`${a.id}:${x.id}`]={masterSha256:String(a.provenance!.masterSha256),cut:x.cut,phraseEnded:true,confirmedAt:'SYNTHETIC-TEST-ONLY'};for(const w of b.windows)if(w.variants[a.id])r.entries![`${b.id}:${w.id}:${a.id}`]={assetSha256:w.variants[a.id].sha256,bodySha256:b.native.sha256,noVocalEntry:true,bodyStartsClean:true,confirmedAt:'SYNTHETIC-TEST-ONLY'}
   const out=guardPlan(c,r,a,c.tracks,0,{kind:'next',targetId:b.id},new Set(),a.duration,false);if(out.best){feasible++;expect(out.best.end).toBeGreaterThanOrEqual((out.best as any).protection.exit.sectionEnd-.001);expect(out.best.midDuck).toBe(false)}
  }
 }
 expect(blocked).toBe(30);expect(feasible).toBeGreaterThan(0);console.log(JSON.stringify({windows,assets,unreviewedBlocked:blocked,syntheticFeasiblePairs:feasible,notHumanValidation:true}))
})
