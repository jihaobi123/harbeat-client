import fs from 'node:fs'
import {createHash} from 'node:crypto'
import {assertSelectionBinding} from '../web/src/vocal-bridge/material'
import {validateBridge} from '../web/src/vocal-bridge/policy'
import {buildV30Eq} from '../web/src/v30/eq'
import {vocalPresence,type Plan,type Track} from '../web/src/realtime/planner'
const [selectionFile,renderedFile,out]=process.argv.slice(2)
const selection=JSON.parse(fs.readFileSync(selectionFile,'utf8')),rendered=JSON.parse(fs.readFileSync(renderedFile,'utf8'))
assertSelectionBinding(rendered.selectionSha256,createHash('sha256').update(fs.readFileSync(selectionFile)).digest('hex'))
const tracks=new Map<string,Track>(selection.tracks.map((t:Track)=>[t.id,t]))
const cases=selection.cases.map((c:any)=>{
 const a=tracks.get(c.a)!,b=tracks.get(c.b)!;validateBridge(a,b,c)
 const av=vocalPresence(a.vocals!,c.start,c.end),bv=vocalPresence(b.vocals!,c.bEntry,c.bEnd)
 const midDuck=av*c.duration>=.5&&av>=.05&&bv*(c.bEnd-c.bEntry)>=.5&&bv>=.05
 const eq=buildV30Eq(a,b,{start:c.start,duration:c.duration,rate:c.rate,midDuck,window:{start:c.bEntry,end:c.bEnd}} as Plan)
 const material=rendered.cases.find((r:any)=>r.id===c.id);if(!material)throw Error('missing rendered case')
 return {...c,...material,pre:4,post:10,restore:4+c.duration-Math.min(c.duration,120/a.bpm),eq:{...eq,evidence:[]},label:c.bEntry<12?'前奏铺入':c.role==='inst'?'间奏铺入':'无人声片段铺入',style:[...new Set([...c.styleA,...c.styleB])].join(' → ')}
})
fs.writeFileSync(out,JSON.stringify({version:'vocal-bridge-v1',selectionSha256:rendered.selectionSha256,cases},null,2))
console.log('Validated and built',cases.length,'cases')
