import type {Asset} from './planner'
import {readEncoded,storeEncoded,deleteEncoded} from './encodedCache'
const fingerprint=async(bytes:ArrayBuffer)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(n=>n.toString(16).padStart(2,'0')).join('')
const pcmBytes=(b:AudioBuffer)=>b.length*b.numberOfChannels*4
/** One bounded PCM pool may outlive a player. No AudioContext or playing node is retained. */
export class AudioBufferPool{
 readonly buffers=new Map<string,AudioBuffer>()
 readonly identities=new Map<string,string>()
 readonly owners=new Set<AudioCache>()
 constructor(readonly limit=192*1024*1024){}
 get bytes(){return [...this.buffers.values()].reduce((sum,b)=>sum+pcmBytes(b),0)}
 delete(key:string){this.buffers.delete(key);this.identities.delete(key)}
 put(key:string,identity:string,buffer:AudioBuffer){
  const existing=this.buffers.get(key)
  if(existing&&this.identities.get(key)===identity)return existing
  if(existing)this.delete(key)
  const pinned=new Set([...this.owners].flatMap(owner=>[...owner.protected]))
  const size=pcmBytes(buffer)
  for(const [k] of this.buffers){if(this.bytes+size<=this.limit)break;if(!pinned.has(k))this.delete(k)}
  if(this.bytes+size>this.limit)throw new Error('内存不足以准备下一首，请停止后重试')
  this.buffers.set(key,buffer);this.identities.set(key,identity);return buffer
 }
}
export class AudioCache{
 private loading=new Map<string,{promise:Promise<AudioBuffer>;controller:AbortController;users:number}>()
 protected=new Set<string>();disposed=false
 readonly pool:AudioBufferPool
 constructor(private ctx:AudioContext,private base:URL,private progress:(s:string)=>void,pool?:AudioBufferPool){this.pool=pool||new AudioBufferPool();this.pool.owners.add(this)}
 get buffers(){return this.pool.buffers}
 get ready(){return new Set(this.buffers.keys())}
 get sizeMB(){return Math.round(this.pool.bytes/1024/1024)}
 async load(asset:Asset,signal?:AbortSignal){
  signal?.throwIfAborted()
  if(this.disposed)throw new Error('播放器已关闭')
  const identity=`${new URL(asset.url,this.base)}|${asset.sha256}|${asset.duration}|${this.ctx.sampleRate}`
  const hit=this.buffers.get(asset.url)
  if(hit&&this.pool.identities.get(asset.url)===identity){this.buffers.delete(asset.url);this.buffers.set(asset.url,hit);this.progress('复用已就绪音频');return hit}
  if(hit)this.pool.delete(asset.url)
  let work=this.loading.get(identity)
  if(work?.controller.signal.aborted)work=undefined
  if(!work){
   const controller=new AbortController()
   const created={controller,users:0,promise:Promise.resolve(null as unknown as AudioBuffer)}
   created.promise=this.fetch(asset,identity,controller).finally(()=>{if(this.loading.get(identity)===created)this.loading.delete(identity)})
   work=created;this.loading.set(identity,created)
  }
  const shared=work;shared.users++
  return new Promise<AudioBuffer>((resolve,reject)=>{
   let finished=false
   const finish=(error:unknown,buffer?:AudioBuffer)=>{if(finished)return;finished=true;signal?.removeEventListener('abort',abort);shared.users--;if(!shared.users&&!this.buffers.has(asset.url))shared.controller.abort();if(error)reject(error);else resolve(buffer!)}
   const abort=()=>finish(signal?.reason||new DOMException('音频准备已取消','AbortError'))
   signal?.addEventListener('abort',abort,{once:true})
   if(signal?.aborted)abort()
   shared.promise.then(buffer=>finish(null,buffer),error=>finish(error))
  })
 }
 private async fetch(asset:Asset,identity:string,controller:AbortController){
  const url=new URL(asset.url,this.base);url.searchParams.set('sha256',asset.sha256)
  let cached=await readEncoded(url.href)
  if(cached&&await fingerprint(cached)!==asset.sha256){await deleteEncoded(url.href);cached=null}
  if(this.disposed)throw new Error('播放器已关闭')
  controller.signal.throwIfAborted()
  this.progress(cached?'正在读取本机音频缓存…':'正在读取音频素材…');const timer=setTimeout(()=>controller.abort(),180000)
  let bytes:ArrayBuffer
  try{
   if(cached){bytes=cached}else{
   const response=await fetch(url,{signal:controller.signal});if(!response.ok)throw new Error('音频读取失败 '+response.status)
   const reader=response.body?.getReader()
   if(reader){const chunks:Uint8Array[]=[];let total=0,last=0
    for(;;){const {done,value}=await reader.read();if(done)break;total+=value.byteLength;if(total>64*1024*1024){await reader.cancel();throw new Error('素材超过本次内存限制')}chunks.push(value)
     if(performance.now()-last>250&&!this.disposed){this.progress(`正在读取音频 ${(total/1048576).toFixed(1)} / ${(asset.bytes/1048576).toFixed(1)} MB…`);last=performance.now()}}
    const joined=new Uint8Array(total);let offset=0;for(const part of chunks){joined.set(part,offset);offset+=part.byteLength}bytes=joined.buffer
   }else bytes=await response.arrayBuffer()
   }
  }finally{clearTimeout(timer)}
  if(bytes.byteLength>64*1024*1024)throw new Error('素材超过本次内存限制')
  const hash=await fingerprint(bytes)
  if(hash!==asset.sha256)throw new Error('音频校验失败，请刷新素材版本')
  if(!cached)void storeEncoded(url.href,bytes).catch(()=>{})
  if(this.disposed)throw new Error('播放器已关闭')
  this.progress('正在解码并核对音频…');const buffer=await this.ctx.decodeAudioData(bytes)
  if(this.disposed)throw new Error('播放器已关闭')
  if(Math.abs(buffer.duration-asset.duration)>.04)throw new Error('解码时长与素材记录不一致')
  controller.signal.throwIfAborted()
  const installed=this.pool.put(asset.url,identity,buffer);this.progress('素材已就绪');return installed
 }
 dispose(){this.disposed=true;for(const work of this.loading.values())work.controller.abort();this.protected.clear();this.pool.owners.delete(this)}
}
