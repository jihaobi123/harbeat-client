import {describe,it,expect} from 'vitest'
import {renderToStaticMarkup} from 'react-dom/server'
import DecisionHistory, {decisionReport} from './DecisionHistory'
const logs=[
 {kind:'request_received',requestId:'r1',intent:{kind:'next'},budgetSec:10,sourcePosition:42,wallTime:'2026-09-21',origin:'user'},
 {kind:'decision_search',requestId:'r1',phase:'preparation_preview',remainingBudgetSec:10,result:{candidateCount:0,candidates:[],exclusions:[{track:'B',code:'deadline',reason:'超过等待预算',count:5}]}},
 {kind:'request_outcome',requestId:'r1',outcome:'failed',reason:'没有可用窗口'},
]
describe('human-readable audit history',()=>{
 it('shows failed triggers and their actual exclusions instead of hiding them',()=>{
  const html=renderToStaticMarkup(<DecisionHistory logs={logs} tracks={[]}/>)
  expect(html).toContain('逐次混音决策日志');expect(html).toContain('没有可用窗口');expect(html).toContain('超过等待预算')
 })
 it('exports every request with stable ids and failure reasons',()=>{
  const text=decisionReport(logs,[]);expect(text).toContain('r1');expect(text).toContain('没有可用窗口');expect(text).toContain('超过等待预算')
 })
})
