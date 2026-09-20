import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import AnalysisLab,{canOpenJobResult} from './AnalysisLab'

describe('analysis platform', () => {
  it('provides import, history and clear evidence boundaries without demo scores', () => {
    const html = renderToStaticMarkup(<AnalysisLab />)
    expect(html).toContain('音乐分析工作台')
    expect(html).toContain('导入分析 JSON')
    expect(html).toContain('搜索曲目')
    expect(html).toContain('HarBeat 标志')
    expect(html).toContain('个版本')
    expect(html).not.toContain('99%')
  })
  it('keeps the audition selection when a background or another track job finishes',()=>{
    const job={id:'job',source_report_id:'A',report_id:'A-new',status:'completed'}
    expect(canOpenJobResult(null,'A',job)).toBe(false)
    expect(canOpenJobResult('job','B',job)).toBe(false)
    expect(canOpenJobResult('job','A',job)).toBe(true)
  })
})
