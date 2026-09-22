import {it,expect} from 'vitest'
import {readFileSync,writeFileSync} from 'node:fs'
import {planNext,type Track,type Intent} from './planner'
const path=process.env.LIVE_CATALOG
it.skipIf(!path)('audits real six-track intentions without changing source assets',()=>{
 const catalog=JSON.parse(readFileSync(path!,'utf8')),tracks:Track[]=catalog.tracks
 const ready=new Set(tracks.flatMap(t=>[t.native.url,...t.windows.flatMap(w=>Object.values(w.variants).map(x=>x.url))]))
 const styles=[...new Set(tracks.flatMap(t=>t.mixProfile!.windows.filter(w=>w.takeover.style.status==='model_candidate').map(w=>w.takeover.style.top[0].style)))]
 const intents:Intent[]=[{kind:'next'},{kind:'up'},{kind:'down'},...styles.flatMap(style=>[{kind:'next' as const,style,energy:'up' as const},{kind:'next' as const,style,energy:'down' as const},{kind:'style' as const,style}])]
 const rows:any[]=[];let maxMs=0
 for(const a of tracks)for(const position of [5,15,30,45,60,80])for(const intent of intents){if(position+18>a.duration)continue;const started=performance.now(),result=planNext(a,tracks,position,intent,ready,18);maxMs=Math.max(maxMs,performance.now()-started)
  if(result.best){const p=result.best;expect(p.start).toBeGreaterThanOrEqual(position+.25);expect(p.end).toBeLessThanOrEqual(position+18);expect(p.evidence?.accepted).toBe(true);if(intent.style)expect(p.evidence!.style.takeover!.top[0].style).toBe(intent.style);if(intent.energy||intent.kind==='up'||intent.kind==='down')expect(p.evidence!.deltasDb.every(x=>x!==null&&Math.abs(x)>=1-1e-9&&Math.abs(x)<=6+1e-9)).toBe(true)}
  rows.push({a:a.title,position,intent,best:result.best?{to:tracks.find(t=>t.id===result.best!.to)?.title,start:result.best.start,end:result.best.end,window:result.best.window.id,evidence:result.best.evidence}:null,exclusions:result.exclusions.map(x=>({track:x.track,window:x.windowId,code:x.code,count:x.count}))})
 }
 const summary={requests:rows.length,accepted:rows.filter(x=>x.best).length,styles,maxPlanningMs:maxMs,byIntent:intents.map(intent=>({intent,requests:rows.filter(x=>JSON.stringify(x.intent)===JSON.stringify(intent)).length,accepted:rows.filter(x=>JSON.stringify(x.intent)===JSON.stringify(intent)&&x.best).length}))}
 console.log(JSON.stringify(summary));if(process.env.LIVE_AUDIT_OUTPUT)writeFileSync(process.env.LIVE_AUDIT_OUTPUT,JSON.stringify({summary,rows},null,2))
},60000)
