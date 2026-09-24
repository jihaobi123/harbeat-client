import type {Track} from '../realtime/planner'
import {loadJson} from '../phrase/load'

export type LibraryEntry={id:string;title:string;bpm:number|null;duration:number|null;style:string|null;collection:string;styleLabels:string[];detailUrl:string;playStatus:'ready'|'unavailable';mixStatus:'ready'|'unavailable';reason?:string}
export type LibraryIndex={schema:string;tracks:LibraryEntry[];coverage?:Record<string,unknown>}
export function readLibraryIndex(value:any):LibraryIndex{
 if(value?.schema!=='harbeat.continuous-library.v1'||!Array.isArray(value.tracks))throw Error('曲库索引格式不完整')
 const ids=new Set<string>()
 for(const row of value.tracks){
  if(!row||typeof row.id!=='string'||!row.id||typeof row.title!=='string'||(row.playStatus==='ready'&&(!Number.isFinite(row.duration)||row.duration<=0||!Number.isFinite(row.bpm)||row.bpm<=0))||!Array.isArray(row.styleLabels)||typeof row.collection!=='string'||!['ready','unavailable'].includes(row.playStatus)||!['ready','unavailable'].includes(row.mixStatus))throw Error('曲库中有不完整的歌曲记录')
  if(ids.has(row.id))throw Error('曲库中有重复的歌曲标识')
  ids.add(row.id)
 }
 return value
}
export class TrackLibrary{
 private loaded=new Map<string,Track>()
 private pending=new Map<string,Promise<Track>>()
 constructor(readonly entries:LibraryEntry[],private base:URL,private read:(file:string,base:URL)=>Promise<any>=loadJson){}
 async load(id:string):Promise<Track>{
  const entry=this.entries.find(t=>t.id===id)
  if(!entry||entry.playStatus!=='ready')throw Error(entry?.reason||'这首歌暂时无法播放')
  const hit=this.loaded.get(id)
  if(hit){this.loaded.delete(id);this.loaded.set(id,hit);return hit}
  const pending=this.pending.get(id);if(pending)return pending
  if(!entry.detailUrl||new URL(entry.detailUrl,this.base).origin!==this.base.origin)throw Error('歌曲资料地址不属于当前曲库')
  const task=this.read(entry.detailUrl,this.base).then(value=>{
   const track=value?.track as Track
   if(!track||track.id!==entry.id||Math.abs(track.duration-entry.duration!)>.05||!track.native||!Array.isArray(track.windows)||!Array.isArray(track.bars))throw Error('歌曲资料与曲库索引不一致')
   this.loaded.set(id,track);return track
  }).finally(()=>this.pending.delete(id))
  this.pending.set(id,task);return task
 }
 values(){return [...this.loaded.values()]}
 trim(pinned:Set<string>,limit=6){for(const [id] of this.loaded){if(this.loaded.size<=limit)break;if(!pinned.has(id))this.loaded.delete(id)}}
}
export function filterLibrary(entries:LibraryEntry[],filters:{collection?:string;label?:string;query?:string}){
 const query=filters.query?.trim().toLocaleLowerCase()||''
 return entries.filter(t=>(!filters.collection||t.collection===filters.collection)&&(!filters.label||t.styleLabels.includes(filters.label))&&(!query||`${t.title} ${t.styleLabels.join(' ')} ${t.collection}`.toLocaleLowerCase().includes(query)))
}
export function suggestNext(entries:LibraryEntry[],current:LibraryEntry,recent:string[]):LibraryEntry|null{
 if(!current.bpm||current.bpm<=0)return null
 const bpm=current.bpm
 const compatible=entries.filter(t=>t.id!==current.id&&t.mixStatus==='ready'&&t.playStatus==='ready'&&typeof t.bpm==='number'&&t.bpm>0&&bpm/t.bpm>=.8&&bpm/t.bpm<=1.2)
 const fresh=compatible.filter(t=>!recent.includes(t.id)),choices=fresh.length?fresh:compatible
 return [...choices].sort((a,b)=>{
  const cost=(t:LibraryEntry)=>Math.abs(Math.log(t.bpm!/bpm))+(t.collection===current.collection?0:.03)+(t.styleLabels.some(x=>current.styleLabels.includes(x))?0:.02)
  return cost(a)-cost(b)||a.id.localeCompare(b.id)
 })[0]||null
}
