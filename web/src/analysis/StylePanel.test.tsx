import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { StyleSources } from './StylePanel'

it('keeps rule matching, dance suitability and original human tags visibly separate',()=>{
 const html=renderToStaticMarkup(<StyleSources evidence={{rules:[{path:'core.genre_profile',raw:{primary_genre:'house',genres:[{name:'house',confidence:1}]}}],dance:[],manual:[{path:'core.genre_profile',labels:['hiphop'],raw:{manual_primary_style:'hiphop'}}],fine_rules:[],metadata:[]}}/>)
 expect(html).toContain('规则判断');expect(html).toContain('相对匹配分');expect(html).toContain('原有人工标签');expect(html).toContain('hiphop');expect(html).toContain('本曲尚无舞种评分记录');expect(html).not.toContain('100%')
})
