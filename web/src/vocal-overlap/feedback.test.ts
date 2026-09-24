import {describe,expect,it} from 'vitest'
import {completedComparison,feedbackKey,readFeedback,writeFeedback,type AuditionRequest} from './feedback'

const request:AuditionRequest={sessionId:'s',requestId:'r',comparisonId:'unique-run',caseKey:'case-a',arm:'variant',a:'a',b:'b',position:30,planId:'candidate'}
const logs=()=>[
 {kind:'request_received',sessionId:'s',requestId:'r',origin:'controlled_comparison',sourceTrackId:'a',sourcePosition:30,intent:{targetId:'b'},experiment:{experimentId:'vocal-overlap-v1',comparisonId:'unique-run',caseKey:'case-a',arm:'variant'}},
 {kind:'plan_scheduled',sessionId:'s',requestId:'r',planId:'execution',plan:{id:'candidate',from:'a',to:'b'}},
 {kind:'request_outcome',sessionId:'s',requestId:'r',planId:'execution',outcome:'completed'},
 {kind:'audio_observation',sessionId:'s',requestId:'r',planId:'execution',name:'A 退出 / B 正文接管'},
 {kind:'comparison_finished',sessionId:'s',comparisonId:'unique-run'},
]
describe('exact controlled audition feedback',()=>{
 it('requires handoff completion, audio observation, and the full preview ending',()=>{
  const full=logs()
  expect(completedComparison(full,request,'case-a','variant')).toMatchObject({requestId:'r',executionId:'execution',arm:'variant'})
  for(const kind of ['request_outcome','audio_observation','comparison_finished'])expect(completedComparison(full.filter(l=>l.kind!==kind),request,'case-a','variant')).toBeNull()
 })
 it('does not attribute a finished old case, arm, session or request to the current controls',()=>{
  expect(completedComparison(logs(),request,'case-b','variant')).toBeNull()
  expect(completedComparison(logs(),request,'case-a','baseline')).toBeNull()
  for(const field of ['sessionId','requestId','comparisonId','planId'] as const)expect(completedComparison(logs(),{...request,[field]:'different'},'case-a','variant')).toBeNull()
  expect(completedComparison(logs(),null,'case-a','variant')).toBeNull()
 })
 it('rejects live requests and mismatched source positions',()=>{
  const live=logs();live[0].origin='user'
  expect(completedComparison(live,request,'case-a','variant')).toBeNull()
  expect(completedComparison(logs(),{...request,position:31},'case-a','variant')).toBeNull()
 })
 it('does not accept an observation from another request with the same execution id',()=>{
  const wrong=logs();wrong[3].requestId='old-request'
  expect(completedComparison(wrong,request,'case-a','variant')).toBeNull()
 })
})
describe('isolated feedback storage',()=>{
 it('reads and writes only the experiment key and preserves other experiment rows',()=>{
  const data=new Map([['harbeat-v30-small-tuning-feedback-v1','old feedback'],[feedbackKey,JSON.stringify({first:{value:'first'}})]]),seen:string[]=[]
  const storage={getItem:(key:string)=>{seen.push(key);return data.get(key)??null},setItem:(key:string,value:string)=>{seen.push(key);data.set(key,value)}}
  expect(readFeedback(storage)).toHaveProperty('first')
  expect(writeFeedback(storage,{second:{value:'second'}})).toEqual({first:{value:'first'},second:{value:'second'}})
  expect(new Set(seen)).toEqual(new Set([feedbackKey]))
  expect(data.get('harbeat-v30-small-tuning-feedback-v1')).toBe('old feedback')
 })
 it('preserves malformed stored feedback instead of silently overwriting it',()=>{
  let raw='[broken';const storage={getItem:()=>raw,setItem:(_key:string,value:string)=>{raw=value}}
  expect(()=>writeFeedback(storage,{new:{value:'new'}})).toThrow()
  expect(raw).toBe('[broken')
 })
})
