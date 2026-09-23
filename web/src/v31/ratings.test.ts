import {describe,it,expect} from 'vitest'
import {readRatings,writeRating,RATINGS_KEY,BACKUP_KEY} from './ratings'
function storage(){const data=new Map<string,string>();return {getItem:(k:string)=>data.get(k)??null,setItem:(k:string,v:string)=>{data.set(k,v)}}}
describe('existing listening feedback',()=>{
 it('keeps the exact original record and a non-overwriting backup',()=>{const s=storage(),raw='{"a|b|30":{"preference":"保护版更好","notes":"尾音好"}}';s.setItem(RATINGS_KEY,raw);expect(readRatings(s)['a|b|30'].notes).toBe('尾音好');expect(s.getItem(RATINGS_KEY)).toBe(raw);expect(s.getItem(BACKUP_KEY)).toBe(raw);writeRating(s,{},'c|d|30',{preference:'V3 更好'});expect(readRatings(s)['a|b|30'].notes).toBe('尾音好');expect(s.getItem(BACKUP_KEY)).toBe(raw)})
 it('merges the latest saved cases rather than a stale tab snapshot',()=>{const s=storage();writeRating(s,{},'first',{preference:'保护版更好'});const result=writeRating(s,{},'second',{preference:'差不多'});expect(Object.keys(result)).toEqual(['first','second'])})
 it('keeps unsaved changes when a later case can be persisted',()=>{const s=storage();writeRating(s,{},'a',{notes:'old'});const dirty={a:{notes:'new unsaved'}};const result=writeRating(s,dirty,'b',{notes:'second case'},dirty);expect(result.a.notes).toBe('new unsaved');expect(readRatings(s).a.notes).toBe('new unsaved')})
 it('preserves malformed original data and refuses to overwrite it',()=>{const s=storage();s.setItem(RATINGS_KEY,'broken');expect(()=>readRatings(s)).toThrow();expect(s.getItem(BACKUP_KEY)).toBe('broken');expect(()=>writeRating(s,{},'new',{})).toThrow();expect(s.getItem(RATINGS_KEY)).toBe('broken')})
})
