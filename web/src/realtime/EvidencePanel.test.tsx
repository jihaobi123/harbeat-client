import {it,expect} from 'vitest'
import {renderToStaticMarkup} from 'react-dom/server'
import EvidencePanel from './EvidencePanel'
import type {Track} from './planner'
it('shows unknown local style before playback without assigning the song label',()=>{
 const style={status:'needs_review',top:[{style:'Trap',score:.12}],reasons:['short_context']}
 const t={title:'Test',mixProfile:{sections:[{index:0,label:'intro',start:0,end:6,style,energy:{dbfs:-16}}],windows:[],source:{reportId:'report-test'},limitations:[]}} as unknown as Track
 const html=renderToStaticMarkup(<EvidencePanel track={t}/>);expect(html).toContain('试听前查看');expect(html).toContain('待确认');expect(html).toContain('片段短于8秒');expect(html).toContain('report-test');expect(html).toContain('-16.0 dBFS')
})
