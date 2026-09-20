import type {Asset} from './planner'
/** Two live decks plus a bounded pool. Loaded PCM is never mistaken for network readiness. */
export class AudioCache{
 buffers=new Map<string,AudioBuffer>();private bytes=0;private loading=new Map<string,Promise<AudioBuffer>>();protected=new Set<string>();disposed=false
 constructor(private ctx:AudioContext,private base:URL,private progress:(s:string)=>void){}
 get ready(){return new Set(this.buffers.keys())}
 get sizeMB(){return Math.round(this.bytes/1024/1024)}
 async load(asset:Asset){
  const hit=this.buffers.get(asset.url);if(hit){this.buffers.delete(asset.url);this.buffers.set(asset.url,hit);return hit}
  const current=this.loading.get(asset.url);if(current)return current
  const work=this.fetch(asset).finally(()=>this.loading.delete(asset.url));this.loading.set(asset.url,work);return work
 }
 private async fetch(asset:Asset){
  if(this.disposed)throw new Error('播放器已关闭')
  this.progress('正在读取音频素材…');const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),90000)
  let bytes:ArrayBuffer
  try{const response=await fetch(new URL(asset.url,this.base),{signal:controller.signal});if(!response.ok)throw new Error('音频读取失败 '+response.status);bytes=await response.arrayBuffer()}finally{clearTimeout(timer)}
  if(bytes.byteLength>64*1024*1024)throw new Error('素材超过本次内存限制')
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(n=>n.toString(16).padStart(2,'0')).join('')
  if(hash!==asset.sha256)throw new Error('音频校验失败，请刷新素材版本')
  this.progress('正在解码并核对音频…');const buffer=await this.ctx.decodeAudioData(bytes)
  if(this.disposed)throw new Error('播放器已关闭')
  if(Math.abs(buffer.duration-asset.duration)>.04)throw new Error('解码时长与素材记录不一致')
  const size=buffer.length*buffer.numberOfChannels*4;const limit=192*1024*1024
  for(const [key,b] of this.buffers){if(this.bytes+size<=limit)break;if(this.protected.has(key))continue;this.buffers.delete(key);this.bytes-=b.length*b.numberOfChannels*4}
  if(this.bytes+size>limit)throw new Error('内存不足以准备下一首，请停止后重试')
  this.buffers.set(asset.url,buffer);this.bytes+=size;this.progress('素材已就绪');return buffer
 }
 dispose(){this.disposed=true;this.buffers.clear();this.bytes=0}
}
