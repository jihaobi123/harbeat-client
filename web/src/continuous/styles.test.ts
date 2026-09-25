import {describe,it,expect} from 'vitest'
import {styleChoices,pickStyle} from './styles'
import type {LibraryEntry} from './catalog'
const e=(id:string,bpm:number,labels:string[],extra:Partial<LibraryEntry>={}):LibraryEntry=>({id,title:id,bpm,style:'Pop',collection:'音乐风格参考曲库',styleLabels:labels,duration:200,detailUrl:`details/${id}.json`,mixStatus:'ready',playStatus:'ready',...extra})
describe('next style is an explicit selection intent',()=>{
 it('uses curated labels, not the model genre or the browsing group',()=>{
  const tracks=[e('a',100,['house']),e('b',101,['KPOP']),e('c',100,['house'],{mixStatus:'unavailable'})]
  expect(styleChoices(tracks)).toEqual([{key:'house',count:1},{key:'KPOP',count:1}])
  expect(pickStyle(tracks,tracks[1],'house',[])?.id).toBe('a')
 })
 it('keeps the requested style and reports an empty compatible pool without silently substituting it',()=>{
  const current=e('a',90,['trap']),tracks=[current,e('b',140,['house']),e('c',95,['trap'])]
  expect(pickStyle(tracks,current,'house',[])).toBeNull()
 })
 it('avoids recent tracks and retains tempo direction rules',()=>{
  const current=e('a',110,['KPOP']),tracks=[current,e('recent',110,['house']),e('fresh',112,['house'])]
  expect(pickStyle(tracks,current,'house',['recent'])?.id).toBe('fresh')
 })
})
