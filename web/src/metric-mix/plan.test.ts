import {expect,it} from 'vitest'
import {canArm,contextForSource,adoptedPosition} from './plan'
it('refuses an expired preparation or wrong current song instead of hard cutting',()=>{
 expect(canArm({from:'a',start:10},'a',9.9)).toBe(false)
 expect(canArm({from:'a',start:10},'b',0)).toBe(false)
 expect(canArm({from:'a',start:10},'a',8)).toBe(true)
})
it('maps source boundaries to one audio clock and adopts native B at the frozen endpoint',()=>{
 expect(contextForSource(5,100,108)).toBe(13)
 expect(adoptedPosition({bEnd:20},13,15)).toBe(22)
})
