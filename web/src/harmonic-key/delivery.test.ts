import {expect,it} from 'vitest'
import {qualityTrack} from '../continuous/qualityFixture'
import type {Plan,Track} from '../realtime/planner'
import {comparisonSources} from '../realtime/comparisonSources'
import {nativeSegment} from '../continuous/segments'

function track(id:string):Track{
 const t=qualityTrack(id);t.duration=220;t.native={url:id+'-first',sha256:id+'-first',duration:150,bytes:1}
 t.audioSegments=[{start:0,end:150,asset:t.native},{start:150,end:220,asset:{url:id+'-last',sha256:id+'-last',duration:70,bytes:1}}]
 return t
}
it('preloads the actual late source and takeover segments without changing timing or source records',()=>{
 const tracks=[track('a'),track('b')],before=JSON.stringify(tracks)
 const p={from:'a',to:'b',start:164,window:{end:170}} as Plan
 const result=comparisonSources(tracks[0],tracks[1],p,0,true)
 expect(result.from.asset.url).toBe('a-last');expect(result.to.asset.url).toBe('b-last')
 expect(nativeSegment(tracks[0],result.offset).asset).toBe(result.from.asset)
 expect(nativeSegment(tracks[1],p.window.end).asset).toBe(result.to.asset)
 expect(result.offset-result.from.start).toBe(10)
 expect(JSON.stringify(tracks)).toBe(before)
})
it('handles an entry immediately before a segment boundary using its actual preceding audio',()=>{
 const tracks=[track('a'),track('b')],p={from:'a',to:'b',start:152,window:{end:20}} as Plan
 const result=comparisonSources(tracks[0],tracks[1],p,0,true)
 expect(result.from.asset.url).toBe('a-first');expect(result.to.asset.url).toBe('b-first')
})

it('preflights every chunk crossed by the complete outgoing and takeover ranges',()=>{
 const tracks=[track('a'),track('b')],p={from:'a',to:'b',start:152,end:156,window:{end:148}} as Plan
 const result=comparisonSources(tracks[0],tracks[1],p,0,true)
 expect(result.assets.map(a=>a.url)).toEqual(['a-first','a-last','b-first','b-last'])
})
