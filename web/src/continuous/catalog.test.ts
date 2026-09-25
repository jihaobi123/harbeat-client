import {describe,it,expect,vi} from 'vitest'
import {readLibraryIndex,TrackLibrary,filterLibrary,suggestNext,refreshLibraryTracks,type LibraryEntry} from './catalog'
import type {Track} from '../realtime/planner'
const entry=(id:string,bpm=100,collection='KPOP'):LibraryEntry=>({id,title:id,bpm,collection,style:'Pop',styleLabels:['KPOP'],duration:200,detailUrl:`tracks/${id}.json`,playStatus:'ready',mixStatus:'ready'})
const detail=(e:LibraryEntry)=>({track:{...e,styleScore:1,native:{url:e.id+'.flac',sha256:'a'.repeat(64),bytes:10,duration:150},bars:[0,2.4],windows:[],sections:[],energy:[],vocals:[]} as Track})
describe('complete library index and lazy detail loading',()=>{
 it('refreshes metadata for the latest live tracks when selection changes during a catalog refresh',async()=>{
  const entries=[entry('a'),entry('b')];let pins=['a'];let finish!:(value:any)=>void
  const lib=new TrackLibrary(entries,new URL('https://example.test/'),file=>file.includes('/a.')?new Promise(r=>{finish=r}):Promise.resolve(detail(entries[1])))
  const refresh=refreshLibraryTracks(lib,()=>pins)
  pins=['b'];finish(detail(entries[0]));await refresh
  expect(lib.values().map(t=>t.id)).toEqual(['a','b'])
 })
 it('retains unavailable songs and rejects duplicate identities',()=>{
  const entries=[entry('a'),{...entry('b'),mixStatus:'unavailable',playStatus:'unavailable',duration:null,bpm:null,reason:'源文件待核验'}]
  expect(readLibraryIndex({schema:'harbeat.continuous-library.v1',tracks:entries}).tracks).toHaveLength(2)
  expect(()=>readLibraryIndex({schema:'harbeat.continuous-library.v1',tracks:[entries[0],entries[0]]})).toThrow(/重复/)
 })
 it('loads only requested tracks and deduplicates in-flight requests',async()=>{
  const a=entry('a'),b=entry('b'),read=vi.fn(async(_file:string,_base:URL)=>detail(a)),library=new TrackLibrary([a,b],new URL('https://example.test/live/'),read)
  const [one,two]=await Promise.all([library.load('a'),library.load('a')])
  expect(one).toBe(two);expect(read).toHaveBeenCalledTimes(1);expect(read.mock.calls[0][0]).toBe('tracks/a.json')
  expect(library.values().map(t=>t.id)).toEqual(['a'])
 })
 it('rejects wrong detail identity and permits retry after a failed fetch',async()=>{
  const a=entry('a'),read=vi.fn().mockResolvedValueOnce(detail(entry('b'))).mockResolvedValueOnce(detail(a))
  const library=new TrackLibrary([a],new URL('https://example.test/live/'),read)
  await expect(library.load('a')).rejects.toThrow(/不一致/)
  expect((await library.load('a')).id).toBe('a')
 })
 it('evicts old detailed analysis but retains the current and next tracks',async()=>{
  const entries=Array.from({length:8},(_,i)=>entry(String(i)))
  const library=new TrackLibrary(entries,new URL('https://example.test/'),async file=>detail(entries.find(e=>e.detailUrl===file)!))
  for(const e of entries)await library.load(e.id)
  library.trim(new Set(['0','1']),4)
  expect(library.values()).toHaveLength(4);expect(library.values().map(t=>t.id)).toEqual(expect.arrayContaining(['0','1']))
 })
})
describe('source labels and next-song suggestions',()=>{
 it('filters manual labels separately from the model style and includes unavailable entries',()=>{
  const entries=[{...entry('Hip Song',95,'音乐风格参考曲库'),styleLabels:['jazz hiphop'],style:'Pop Rap'},entry('K Song')]
  expect(filterLibrary(entries,{collection:'音乐风格参考曲库',label:'jazz hiphop',query:'hip'}).map(e=>e.id)).toEqual(['Hip Song'])
  expect(filterLibrary(entries,{label:'Pop Rap'})).toEqual([])
 })
 it('avoids current/recent/unavailable songs and applies the real tempo direction',()=>{
  const current=entry('a',100),entries=[current,entry('recent',100),entry('near',101),entry('too-fast',130),{...entry('pending',99),mixStatus:'unavailable' as const}]
  expect(suggestNext(entries,current,['recent'])?.id).toBe('near')
  expect(suggestNext([current,entry('too-fast',130)],current,[])).toBeNull()
 })
})

it('shortlists eight compatible tracks while respecting exact song and style constraints',async()=>{
 const {shortlistNext}=await import('./catalog')
 const current=entry('a'),rows=[current,...Array.from({length:12},(_,i)=>entry('b'+i,100+i))]
 expect(shortlistNext(rows,current,[])).toHaveLength(8)
 expect(shortlistNext(rows,current,[],{targetId:'b11'}).map(e=>e.id)).toEqual(['b11'])
 expect(shortlistNext(rows,current,[],{style:'house'})).toEqual([])
 expect(shortlistNext(rows,current,['b0']).some(e=>e.id==='b0')).toBe(false)
})
