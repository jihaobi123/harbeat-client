import {it,expect} from 'vitest'
import {renderToStaticMarkup} from 'react-dom/server'
import {associateTrack,executionRows,MaterialEvidence,SessionEvidence} from './MixTracePanel'
const t:any={id:'t',title:'same name',reportId:'old',provenance:{masterSha256:'audio'},native:{sha256:'clip',url:'/media/a',duration:30,bytes:1},windows:[],sections:[],mixProfile:{source:{masterSha256:'audio'},sections:[],windows:[],energyCurve:[]}}
it('binds material by source identity and exposes changed report versions',()=>{
 expect(associateTrack([t],{id:'new',title:'same name',audio:{sha256:'other'},documents:{}} as any)).toBeNull()
 expect(associateTrack([t],{id:'new',audio:{sha256:'audio'},documents:{}} as any)?.binding).toBe('same_audio_other_version')
 expect(associateTrack([t],{id:'old',audio:{sha256:'other'},documents:{}} as any)).toBeNull()
})
it('does not attach an observation from another plan or fabricate execution',()=>{
 const logs:any[]=[{kind:'plan_scheduled',requestId:'r',planId:'p',events:[{name:'B 开始混入',time:10}]},{kind:'audio_observation',requestId:'r',planId:'other',name:'B 开始混入',plannedContextSec:10,observedContextSec:11}]
 expect(executionRows(logs)[0].actual).toBeNull()
 logs.push({kind:'audio_observation',requestId:'r',planId:'p',name:'B 开始混入',observedContextSec:10.002})
 expect(executionRows(logs)[0].deltaMs).toBeCloseTo(2)
})
it('renders both raw-source and preprocessing links before listening',()=>{
 const html=renderToStaticMarkup(<MaterialEvidence track={t}/>);expect(html).toContain('原始分析报告');expect(html).toContain('audio');expect(html).toContain('clip');expect(html).toContain('分轨')
})
it('shows failed triggers and explicitly marks missing audio-thread records',()=>{
 const session:any={schema:'harbeat.v3_live_session.v2',sessionId:'s',catalog:[t],logs:[{kind:'request_received',requestId:'r',wallTime:'today',intent:{kind:'next'},sourceTrackId:'t',sourcePosition:4,budgetSec:18},{kind:'request_outcome',requestId:'r',outcome:'failed',reason:'no candidate'},{kind:'plan_scheduled',requestId:'old',planId:'p',plan:{from:'t',to:'t'},events:[{name:'event',time:10}]}]}
 const html=renderToStaticMarkup(<SessionEvidence session={session}/>);expect(html).toContain('no candidate');expect(html).toContain('未观察到');expect(html).toContain('原始分析报告')
})
