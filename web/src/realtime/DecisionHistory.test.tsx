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

it('labels controlled playback and retains both plans with observed timing',()=>{
 const controlled:any[]=[
  {kind:'comparison_analysis',comparisonId:'trial:variant',experimentId:'vocal',arm:'variant',comparison:{searches:{variant:{rejected:['different-score']}}}},
  {kind:'request_received',requestId:'c1',origin:'controlled_comparison',intent:{kind:'next'},budgetSec:18,sourcePosition:15,experiment:{comparisonId:'trial:variant',experimentId:'vocal',arm:'variant'}},
  {kind:'audio_observation',requestId:'c1',name:'B 开始混入',plannedContextSec:5,observedContextSec:5.002,observationDeltaMs:2},
 ];
 const html=renderToStaticMarkup(<DecisionHistory logs={controlled} tracks={[]}/>),report=decisionReport(controlled,[]);
 expect(html).toContain('受控试听');expect(html).toContain('different-score');expect(html).toContain('5.002');expect(html).toContain('计划 / 实际观察');
 expect(report).toContain('受控试听');expect(report).toContain('different-score');
});
