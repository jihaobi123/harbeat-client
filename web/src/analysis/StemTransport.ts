/** Decoded stems share one audio clock. Solo never changes sources or their offsets. */
export type StemTrack = {name:string;url:string;duration?:number;channels?:number}
export type LoadProgress = {name:string;phase:'fetching'|'decoding'|'ready';bytes:number;total:number}
const STEMS=['vocals','drums','bass','other']
const MAX_PCM_BYTES=768*1024*1024

export class StemTransport {
  private buffers=new Map<string,AudioBuffer>()
  private nodes=new Map<string,{source:AudioBufferSourceNode;gain:GainNode}>()
  private abort=new AbortController()
  private queue:Promise<void>=Promise.resolve()
  private disposed=false
  private offset=0
  private startedAt=0
  private revision=0
  private pcmBytes=0
  private wantsPlayback=false
  playing=false
  selection='master'
  constructor(private context:AudioContext,private fetcher:typeof fetch=fetch) {}
  get readyNames(){return [...this.buffers.keys()]}
  get duration(){return this.buffers.get('master')?.duration||Math.max(0,...[...this.buffers.values()].map(b=>b.duration))}
  get position(){return Math.min(this.duration,Math.max(0,this.offset+(this.playing?Math.max(0,this.context.currentTime-this.startedAt):0)))}
  async activate(){if(!this.disposed)await this.context.resume()}
  prepare(tracks:StemTrack[],progress?:(p:LoadProgress)=>void):Promise<void> {
    const work=async()=>{
      for(const track of tracks){
        if(this.disposed)throw new Error('已离开当前歌曲')
        if(this.buffers.has(track.name))continue
        const estimate=(track.duration||0)*(track.channels||2)*this.context.sampleRate*4
        if(this.pcmBytes+estimate>MAX_PCM_BYTES)throw new Error('音轨超过本次同步试听的内存上限，请保留已准备的音轨或使用原曲试听')
        const controller=new AbortController()
        const cancel=()=>controller.abort()
        this.abort.signal.addEventListener('abort',cancel,{once:true})
        const timeout=setTimeout(cancel,180000)
        try {
          progress?.({name:track.name,phase:'fetching',bytes:0,total:0})
          const fetcher=this.fetcher
          const response=await fetcher(track.url,{signal:controller.signal,credentials:'same-origin'})
          if(!response.ok)throw new Error(`音轨读取失败（${response.status}）`)
          const total=Number(response.headers.get('content-length'))||0
          // Bound the compressed input too; NAS may contain long lossless recordings.
          if(total>MAX_PCM_BYTES)throw new Error('音频文件超过内存上限')
          const reader=response.body?.getReader();let data:ArrayBuffer
          if(reader){
            const chunks:Uint8Array[]=[];let bytes=0
            while(true){const {value,done}=await reader.read();if(done)break;bytes+=value.byteLength
              if(bytes>MAX_PCM_BYTES){controller.abort();throw new Error('音频文件超过内存上限')}
              chunks.push(value);progress?.({name:track.name,phase:'fetching',bytes,total})
            }
            const joined=new Uint8Array(bytes);let at=0
            for(const chunk of chunks){joined.set(chunk,at);at+=chunk.length}
            chunks.length=0;data=joined.buffer
          }else data=await response.arrayBuffer()
          if(this.disposed)throw new Error('已离开当前歌曲')
          progress?.({name:track.name,phase:'decoding',bytes:data.byteLength,total:data.byteLength})
          const buffer=await this.context.decodeAudioData(data)
          if(this.disposed)throw new Error('已离开当前歌曲')
          const bytes=buffer.length*buffer.numberOfChannels*4
          if(this.pcmBytes+bytes>MAX_PCM_BYTES)throw new Error('解码后的音轨超过内存上限')
          this.buffers.set(track.name,buffer);this.pcmBytes+=bytes
          if(this.playing){const when=this.context.currentTime+.03;this.startTrack(track.name,buffer,when,this.offset+Math.max(0,when-this.startedAt))}
          progress?.({name:track.name,phase:'ready',bytes:0,total:0})
        } catch(error) {
          throw new Error(`${track.name}：${this.disposed?'已离开当前歌曲':controller.signal.aborted?'读取已取消或超过 3 分钟，请重试':(error as Error).message}`)
        } finally {clearTimeout(timeout);this.abort.signal.removeEventListener('abort',cancel)}
      }
    }
    const result=this.queue.then(work,work);this.queue=result.catch(()=>{});return result
  }
  private level(name:string){return this.selection==='mix'?(STEMS.includes(name)?1:0):(name===this.selection?1:0)}
  select(name:string){
    if(name==='mix'?!STEMS.every(s=>this.buffers.has(s)):!this.buffers.has(name))throw new Error('该音轨尚未准备完成')
    this.selection=name
    const now=this.context.currentTime
    for(const [key,{gain}] of this.nodes){
      const param=gain.gain
      if(param.cancelAndHoldAtTime)param.cancelAndHoldAtTime(now)
      else {param.cancelScheduledValues(now);param.setValueAtTime(param.value,now)}
      param.linearRampToValueAtTime(this.level(key),now+.02)
    }
  }
  private startTrack(name:string,buffer:AudioBuffer,when:number,offset:number){
    if(offset>=buffer.duration)return
    const source=this.context.createBufferSource(),gain=this.context.createGain()
    source.buffer=buffer;gain.gain.setValueAtTime(this.level(name),when)
    source.connect(gain);gain.connect(this.context.destination)
    source.start(when,offset);this.nodes.set(name,{source,gain})
  }
  async play(){
    if(this.disposed||this.playing||!this.buffers.size)return
    this.wantsPlayback=true
    const revision=++this.revision;await this.context.resume()
    if(this.disposed||revision!==this.revision)return
    if(this.offset>=this.duration)this.offset=0
    this.startedAt=this.context.currentTime+.03;this.playing=true
    for(const [name,buffer] of this.buffers)this.startTrack(name,buffer,this.startedAt,this.offset)
  }
  pause(){
    ++this.revision;this.offset=this.position;this.playing=false;this.wantsPlayback=false
    for(const {source,gain} of this.nodes.values()){source.stop();source.disconnect();gain.disconnect()}
    this.nodes.clear()
  }
  async seek(time:number){
    const resume=this.wantsPlayback;this.pause();this.offset=Math.max(0,Math.min(Number.isFinite(time)?time:0,this.duration))
    if(resume&&this.offset<this.duration)await this.play()
  }
  dispose(){this.pause();this.disposed=true;this.abort.abort();this.buffers.clear();this.pcmBytes=0;void this.context.close().catch(()=>{})}
}
