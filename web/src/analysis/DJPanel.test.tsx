import { expect,it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { DJReadiness,PlanPreview,regularGrid,CalibrationGuard } from './DJPanel'

it('keeps missing vocal intervals and role failures visible before playback',()=>{
 const html=renderToStaticMarkup(<DJReadiness data={{review:{status:'stale'},roles:{incoming:{status:'blocked',bar_count:null,issues:[{code:'intro_not_followed_by_verse',message:'前奏结束后不是第一遍主歌'}]},outgoing:{status:'needs_review',bar_count:8,issues:[]}},vocals:{status:'unavailable',intervals:null}}}/> )
 expect(html).toContain('前奏结束后不是第一遍主歌');expect(html).toContain('未知');expect(html).toContain('已过期');expect(html).not.toContain('无人声')
})

it('never fills actual event times from the plan',()=>{
 const html=renderToStaticMarkup(<PlanPreview plan={{status:'needs_review',issues:[],events:[{event_id:'x',name:'完成交接',planned_sec:48,actual_sec:null}],execution:{status:'not_run'}}}/> )
 expect(html).toContain('计划发生时间');expect(html).toContain('实际发生时间');expect(html).toContain('未执行');expect(html).toContain('播放器执行日志尚未接入')
})

it('constant grid uses explicit first downbeat and preserves pickup time',()=>{
 const g=regularGrid(120,.5,8)
 expect(g.downbeats).toEqual([.5,2.5,4.5,6.5]);expect(g.beats[0]).toBe(.5)
 expect(()=>regularGrid(0,0,8)).toThrow();expect(()=>regularGrid(120,9,8)).toThrow()
})

it('blocks calibration while an unrelated local file is being auditioned',()=>{
 const html=renderToStaticMarkup(<CalibrationGuard matches={false}><button>保存校准</button></CalibrationGuard>)
 expect(html).toContain('disabled');expect(html).toContain('返回报告原曲');expect(html).toContain('本地文件')
})
