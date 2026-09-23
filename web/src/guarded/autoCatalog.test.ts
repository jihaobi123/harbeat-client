import {it,expect} from 'vitest'
import {readFileSync} from 'node:fs'
import {guardPlan,type GuardCatalog} from './planner'
it.skipIf(!process.env.AUTO_CATALOG)('finds executable real pairs without any human confirmation',()=>{
 const c=JSON.parse(readFileSync(process.env.AUTO_CATALOG!,'utf8')) as GuardCatalog;const pairs=[]
 for(const a of c.tracks)for(const b of c.tracks){if(a.id===b.id)continue;const r=guardPlan(c,{},a,c.tracks,0,{kind:'next',targetId:b.id},new Set(),a.duration,false);if(!r.best)continue;const p=r.best;expect(p.end).toBeGreaterThanOrEqual((p as any).protection.exit.sectionEnd);expect(p.decision?.policyVersion).toBe('protected-auto-v1');expect((p as any).protection.exitReview).toBeNull();expect(b.vocals?.some(([s,e])=>e>p.window.start&&s<p.window.end+.1)).toBe(false);pairs.push({from:a.title,to:b.title,start:p.start,end:p.end,body:p.window.end})}
 expect(pairs.length).toBeGreaterThanOrEqual(2);expect(pairs.some(x=>x.from==='Cold'&&x.to==='Crazy Love')).toBe(true);expect(pairs.some(x=>x.from==='Crazy Love'&&x.to==='Cold')).toBe(true);console.log(JSON.stringify(pairs,null,2))
})
