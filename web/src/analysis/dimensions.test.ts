import { describe,it,expect } from 'vitest'
import { flatten } from './data'
import { groupRows,dimension } from './dimensions'
describe('complete source dimensions',()=>{
  it('retains every original field including unknown future fields',()=>{
    const rows=flatten({core:{bpm:120,future:[1,2],vocal_events:[{start:0,end:2}]},'instrument-analysis':{bars:[{drum_events:[{time_sec:1,confidence:.2}]}]}})
    const groups=groupRows(rows)
    expect(Object.values(groups).flat().length).toBe(rows.length)
    expect(groups.instruments.length).toBe(2)
    expect(dimension('/vocal_activity/intervals/0/start_ms')).toBe('vocals')
    expect(dimension('/core/transition_windows/0/energy')).toBe('mixing')
  })
})
