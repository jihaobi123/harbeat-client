import type {Log} from '../realtime/transport'
export function completedAudition(logs:Log[]){
 const done=logs.filter(l=>l.kind==='request_outcome'&&l.outcome==='completed').at(-1)
 if(!done)return null
 const execution=logs.find(l=>l.kind==='plan_scheduled'&&l.planId===done.planId&&l.requestId===done.requestId)
 const request=logs.find(l=>l.kind==='request_received'&&l.requestId===done.requestId)
 const observed=logs.some(l=>l.kind==='audio_observation'&&l.planId===done.planId&&l.name==='A 退出 / B 正文接管')
 if(!execution||!request||!observed)return null
 return {a:execution.plan.from,b:execution.plan.to,position:request.sourcePosition,planId:execution.plan.id,executionId:done.planId,sessionId:done.sessionId}
}
