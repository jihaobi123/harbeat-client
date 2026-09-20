import { Report } from './data'
import { sourceNames } from './dimensions'

const labels:Record<string,string>={ready:'已产出',completed:'已完成',degraded:'有降级项',failed:'失败',unavailable:'不可用',pending:'待处理',done:'已完成'}
export default function SourceStatus({report}:{report:Report}) {
  return <section className="lab-panel lab-source-status"><div className="lab-panel-title"><h2>已有分析来源</h2><span>原始判断与降级信息均保留</span></div>
    <div className="lab-source-grid">{Object.entries(report.documents).map(([name,doc])=>{
      const quality=doc.quality||{}, flags=quality.quality_flags||doc.quality_flags||doc.warnings||[]
      const status=doc.status||doc.analysis_status
      const modules=quality.modules||doc.models||doc.pipeline
      return <details key={name}><summary><b>{sourceNames[name]||name}</b><span>{labels[status]||status||'已接入'}</span></summary>
        {doc.error&&<p className="lab-alert">{String(doc.error)}</p>}
        {Array.isArray(flags)&&flags.length>0&&<ul>{flags.map((flag:any,i:number)=><li key={i}>{typeof flag==='string'?flag:JSON.stringify(flag)}</li>)}</ul>}
        {modules&&<pre>{JSON.stringify(modules,null,2)}</pre>}
        {name==='source_binding_notes'&&<pre>{JSON.stringify(doc,null,2)}</pre>}
        <p className="lab-muted">该来源的全部字段可在「全部维度」查看和导出。</p>
      </details>
    })}</div>
  </section>
}
