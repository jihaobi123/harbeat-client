import {expect,it} from 'vitest'
import {echoTreatment,validateEcho} from './policy'
const e={tailEnd:6,nextOnset:13,fadeStart:6.5,fadeEnd:6.7},fx={sendStart:9.5,sendEnd:10,wetStart:9.75,wetEnd:10.79,taps:[{delaySeconds:.25,gain:.26},{delaySeconds:.5,gain:.117},{delaySeconds:.75,gain:.052}]}
it('keeps all dry stem curves identical while enabling only wet signal',()=>{const a=echoTreatment(4,8,{duckStart:2,swapStart:3,swapEnd:4},'reference','natural',6,e,fx),b=echoTreatment(4,8,{duckStart:2,swapStart:3,swapEnd:4},'reference','relay',6,e,fx);expect(a.dry).toEqual(b.dry);expect(a.wet).toBe(0);expect(b.wet).toBe(1)})
it('rejects insufficient wet-tail budget and mismatched protected tail',()=>{expect(()=>validateEcho(4,8,e,{...fx,wetEnd:12})).toThrow();expect(()=>validateEcho(4,8,e,{...fx,sendEnd:10.3})).toThrow()})
