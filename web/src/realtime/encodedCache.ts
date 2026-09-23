/** Separate from ratings/localStorage and the IndexedDB decision log. Best effort only. */
export const AUDIO_CACHE_NAME='harbeat-verified-audio-v1'
let writes=Promise.resolve()
export async function readEncoded(url:string):Promise<ArrayBuffer|null>{
 try{if(typeof caches==='undefined')return null;const hit=await (await caches.open(AUDIO_CACHE_NAME)).match(url);return hit?await hit.arrayBuffer():null}catch{return null}
}
export async function deleteEncoded(url:string){try{if(typeof caches!=='undefined')await (await caches.open(AUDIO_CACHE_NAME)).delete(url)}catch{}}
export async function storeEncoded(url:string,bytes:ArrayBuffer,limit=256*1024*1024){
 const copy=bytes.slice(0)
 writes=writes.then(async()=>{
  if(typeof caches==='undefined'||copy.byteLength>limit)return
  const cache=await caches.open(AUDIO_CACHE_NAME)
  if(await cache.match(url))return
  const keys=await cache.keys(),sizes=await Promise.all(keys.map(async key=>Number((await cache.match(key))?.headers.get('Content-Length'))||0))
  let total=sizes.reduce((a,b)=>a+b,0)
  for(let i=0;i<keys.length&&(total+copy.byteLength>limit||keys.length-i>=256);i++){await cache.delete(keys[i]);total-=sizes[i]}
  await cache.put(url,new Response(copy,{headers:{'Content-Type':'audio/flac','Content-Length':String(copy.byteLength)}}))
 }).catch(()=>{/* Disk quota/privacy settings cannot prevent listening. */})
 await writes
}
