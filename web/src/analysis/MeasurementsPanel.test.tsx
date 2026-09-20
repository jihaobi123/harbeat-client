import { expect,it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import MeasurementsPanel from './MeasurementsPanel'

it('shows measurement definitions and N without claiming calibrated chord confidence',()=>{
 const r:any={summary:{duration:10},extensions:{chords:{status:'ready',data:{segments:[{start:0,end:2,label:'N',confidence:null}]}},measurements:{status:'ready',data:{dynamics:{rms_p95_p5_db:6,relative_silence_ratio:.2,points:[],sections:[]},onsets:{events_per_minute:60,windows:[]}}}}}
 const html=renderToStaticMarkup(<MeasurementsPanel report={r} cursor={0} onSeek={()=>{}} onRun={async()=>{}} busy={false}/> )
 expect(html).toContain('N');expect(html).toContain('6.00');expect(html).toContain('不是 EBU LRA');expect(html).toContain('尚无可用情绪摘要');expect(html).not.toContain('准确率')
})

it('does not draw RMS interpolation across silent gaps',async()=>{
 const { Curve }=await import('./Charts')
 const html=renderToStaticMarkup(<Curve title="RMS" points={[{time:0,value:-10},{time:1,value:-20}]} duration={2} cursor={0} onSeek={()=>{}} maxGapSec={.1}/> )
 expect(html).toMatch(/d="M[^\"]* M/)
})
