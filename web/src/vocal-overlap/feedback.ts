import {completedAudition} from '../v30/feedback'
import type {Log} from '../realtime/transport'

export const feedbackKey='harbeat-vocal-overlap-feedback-v1'
export type Arm='baseline'|'variant'
export type AuditionRequest={sessionId:string;requestId:string;comparisonId:string;caseKey:string;arm:Arm;a:string;b:string;position:number;planId:string}
export function completedComparison(logs:Log[],expected:AuditionRequest|null,caseKey:string,arm:Arm){
 if(!expected||expected.caseKey!==caseKey||expected.arm!==arm)return null
 const scoped=logs.filter(l=>l.sessionId===expected.sessionId&&l.requestId===expected.requestId)
 const request=scoped.find(l=>l.kind==='request_received')
 if(!request||request.origin!=='controlled_comparison'||request.sourceTrackId!==expected.a||request.intent?.targetId!==expected.b||request.sourcePosition!==expected.position||request.experiment?.experimentId!=='vocal-overlap-v1'||request.experiment?.comparisonId!==expected.comparisonId||request.experiment?.caseKey!==caseKey||request.experiment?.arm!==arm)return null
 const done=completedAudition(scoped)
 if(!done||done.a!==expected.a||done.b!==expected.b||done.position!==expected.position||done.planId!==expected.planId)return null
 const ended=logs.some(l=>l.kind==='comparison_finished'&&l.sessionId===expected.sessionId&&l.comparisonId===expected.comparisonId)
 return ended?{...expected,executionId:done.executionId}:null
}
type Store=Pick<Storage,'getItem'|'setItem'>
export type Feedback=Record<string,Record<string,unknown>>
export function readFeedback(store:Store):Feedback{
 const value=JSON.parse(store.getItem(feedbackKey)||'{}')
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error('本轮反馈格式异常，原始记录已保留。')
 return value
}
export function writeFeedback(store:Store,changed:Feedback):Feedback{
 const next={...readFeedback(store),...changed}
 store.setItem(feedbackKey,JSON.stringify(next));return next
}
