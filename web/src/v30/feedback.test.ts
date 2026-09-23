import {it,expect} from 'vitest'
import {completedAudition} from './feedback'
it('only rates a completed and observed transition, never a scheduled/cancelled audition',()=>{
 const logs:any[]=[{kind:'request_received',requestId:'r',sourcePosition:30},{kind:'plan_scheduled',requestId:'r',planId:'p',plan:{id:'candidate',from:'a',to:'b'}}]
 expect(completedAudition(logs)).toBeNull()
 expect(completedAudition([...logs,{kind:'request_outcome',requestId:'r',planId:'p',outcome:'cancelled'}])).toBeNull()
 logs.push({kind:'request_outcome',requestId:'r',planId:'p',outcome:'completed'});expect(completedAudition(logs)).toBeNull()
 logs.push({kind:'audio_observation',planId:'p',name:'A 退出 / B 正文接管'});expect(completedAudition(logs)).toMatchObject({a:'a',b:'b',position:30,planId:'candidate'})
})
