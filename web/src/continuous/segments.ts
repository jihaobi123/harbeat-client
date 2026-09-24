import type {Asset,Track} from '../realtime/planner'
export type NativeSegment={start:number;end:number;asset:Asset}
const SAMPLE=1/44100
/** Source ranges are sample-bound, and all native chunks use the source's original speed. */
export function nativeSegments(track:Track):NativeSegment[]{
 const segments=track.audioSegments
 if(!segments)return [{start:0,end:track.duration,asset:track.native}]
 if(!segments.length)throw new Error('整曲音频分段为空')
 let end=0
 for(const s of segments){if(!Number.isFinite(s.start)||!Number.isFinite(s.end)||s.end<=s.start||Math.abs(s.start-end)>SAMPLE||Math.abs(s.end-s.start-s.asset.duration)>SAMPLE)throw new Error('整曲音频分段必须连续并匹配素材时长');end=s.end}
 if(Math.abs(end-track.duration)>SAMPLE||segments[0].asset.url!==track.native.url||segments[0].asset.sha256!==track.native.sha256)throw new Error('整曲音频分段与原曲记录不一致')
 return segments
}
export function nativeSegment(track:Track,position:number){const segments=nativeSegments(track);return segments.find(s=>s.end>position)||segments[segments.length-1]}
type SchedulerIO={now:()=>number;load:(asset:Asset,signal:AbortSignal)=>Promise<AudioBuffer>;schedule:(buffer:AudioBuffer,at:number,offset:number,duration:number,edge:boolean)=>()=>void;changed:()=>void;scheduled?:(event:{asset:Asset;sourceStart:number;sourceEnd:number;at:number})=>void}
/** At most the current and next native chunk are held by this scheduler. */
export class SegmentScheduler{
 private segments:NativeSegment[];private initial:number;private covered:number;private loaded=new Map<number,{release:()=>void}>();private loading:number|null=null;private controller=new AbortController();private dead=false
 error:string|null=null;late=false
 constructor(private track:Track,readonly at:number,readonly offset:number,private io:SchedulerIO){this.segments=nativeSegments(track);this.initial=this.segments.findIndex(s=>s.end>offset);if(this.initial<0)throw new Error('播放位置超出整曲范围');this.covered=this.initial-1}
 get pins(){if(this.dead)return new Set<string>();return new Set([...this.loaded.keys(),...(this.loading===null?[]:[this.loading])].map(i=>this.segments[i].asset.url))}
 get deadline(){return this.covered===this.segments.length-1?Infinity:this.at+((this.covered<this.initial?this.offset:this.segments[this.covered].end)-this.offset)}
 get coveredSourceEnd(){return this.covered<this.initial?this.offset:this.segments[this.covered].end}
 begin(buffer:AudioBuffer,edge=true){this.install(this.initial,buffer,edge);this.pump()}
 private install(index:number,buffer:AudioBuffer,edge=false){const s=this.segments[index],offset=index===this.initial?this.offset-s.start:0,at=this.at+Math.max(0,s.start-this.offset);this.loaded.set(index,{release:this.io.schedule(buffer,at,offset,s.end-s.start-offset,edge)});this.covered=index;this.io.scheduled?.({asset:s.asset,sourceStart:s.start+offset,sourceEnd:s.end,at})}
 pump(){
  if(this.dead)return
  const now=this.io.now(),position=this.offset+Math.max(0,now-this.at)
  for(const [index,entry] of this.loaded){if(this.segments[index].end<=position&&index<this.covered){entry.release();this.loaded.delete(index)}}
  const next=this.covered+1
  if(this.loading!==null||this.error||this.late||next>=this.segments.length||this.segments[next].start-position>30)return
  // Never prefetch a second future chunk: two pinned files also bound WebAudio's own buffer references.
  if(this.loaded.size>=2)return
  this.loading=next;this.io.changed()
  void this.io.load(this.segments[next].asset,this.controller.signal).then(buffer=>{
   if(this.dead)return
   if(this.io.now()>this.at+this.segments[next].start-this.offset){this.late=true;return}
   this.install(next,buffer)
  }).catch(error=>{if(!this.dead)this.error=error instanceof Error?error.message:String(error)}).finally(()=>{if(!this.dead){this.loading=null;this.io.changed()}})
 }
 retry(){if(this.dead)return;this.error=null;this.pump()}
 dispose(){this.dead=true;this.controller.abort();this.loaded.clear();this.loading=null}
}
