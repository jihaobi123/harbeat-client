export type Asset={url:string;sha256:string;duration:number;bytes:number;rate?:number}
export type Window={id:string;start:number;end:number;bars:number;role:string;energy:number;variants:Record<string,Asset&{rate:number}>}
export type Track={id:string;title:string;bpm:number;style:string;styleScore:number;duration:number;native:Asset;bars:number[];sections:{start:number;end:number;label:string}[];vocals:[number,number][]|null;energy:{start:number;end:number;value:number}[];windows:Window[];warnings?:string[];reportId?:string}
export type Intent={kind:'next'|'up'|'down'|'style';style?:string;targetId?:string}
export type Plan={id:string;from:string;to:string;window:Window;asset:Asset;start:number;end:number;duration:number;restore:number;rate:number;score:number;midDuck:boolean;aVocal:number;bVocal:number;aEnergy:number;bEnergy:number;gridError:number;reason:string;section:string;prepared:boolean}
export function vocalPresence(intervals:[number,number][],start:number,end:number):number{
 const padded=intervals.map(([s,e])=>[Math.max(start,s-.3),Math.min(end,e+.3)]).filter(([s,e])=>e>s).sort((a,b)=>a[0]-b[0]);let total=0,last=-Infinity
 for(const [s,e] of padded){total+=Math.max(0,e-Math.max(s,last));last=Math.max(last,e)}
 return total/Math.max(.001,end-start)
}
export function energyAt(t:Track,start:number,end:number){let sum=0,weight=0;for(const e of t.energy){const w=Math.max(0,Math.min(end,e.end)-Math.max(start,e.start));sum+=w*e.value;weight+=w}return weight?sum/weight:NaN}
export function planNext(a:Track,tracks:Track[],position:number,intent:Intent,ready:Set<string>,budget=18,requireReady=true){
 const candidates:Plan[]=[];const rejected:{track:string;reason:string}[]=[];const reject=(t:Track,reason:string)=>rejected.push({track:t.title,reason});const ae=energyAt(a,position,position+8)
 if(!a.bars.length||a.vocals===null||!Number.isFinite(ae))return {best:null,candidates,rejected:[{track:a.title,reason:'当前曲目缺少拍点、人声或局部能量依据'}]}
 for(const b of tracks){
  if(b.id===a.id)continue
  if(intent.targetId&&b.id!==intent.targetId)continue
  if(intent.kind==='style'&&b.style!==intent.style)continue
  if(b.vocals===null){reject(b,'缺少人声区间');continue}
  let viable=false
  for(const w of b.windows){const asset=w.variants[a.id];if(!asset)continue;const d=asset.duration;const rate=asset.rate
   const prepared=ready.has(asset.url)&&ready.has(b.native.url)
   if(requireReady&&!prepared)continue
   if(!Number.isFinite(d)||d<.5||rate<.8||rate>1.2||b.duration-w.end<12)continue
   if(intent.kind==='up'&&w.energy<ae+.025)continue
   if(intent.kind==='down'&&w.energy>ae-.025)continue
   for(const out of a.bars){const start=out-d;if(start<position+.25||out>position+budget||out>=a.duration-.1)continue
    const gridError=Math.min(...a.bars.map(x=>Math.abs(x-start)));if(gridError>.065)continue
    const av=vocalPresence(a.vocals,start,out),bv=vocalPresence(b.vocals,w.start,w.end)
    const midDuck=av*d>=.5&&av>=.05&&bv*(w.end-w.start)>=.5&&bv>=.05
    const boundary=Math.min(...a.sections.flatMap(s=>[Math.abs(s.start-out),Math.abs(s.end-out)]))<.4
    const section=a.sections.find(s=>s.start<=out&&s.end>out)?.label||'边界'
    const wait=out-position
    const score=1-wait/budget*.5-Math.abs(rate-1)*1.4-av*bv*.3+(boundary?.16:0)+(w.bars===4?.05:0)+(a.style===b.style?.04:0)
    candidates.push({id:`${a.id}:${b.id}:${w.id}:${out.toFixed(3)}`,from:a.id,to:b.id,window:w,asset,start,end:out,duration:d,restore:out-Math.min(d,120/a.bpm),rate,score,midDuck,aVocal:av,bVocal:bv,aEnergy:ae,bEnergy:w.energy,gridError,section,prepared,reason:`${boundary?'段落边界附近':'原始小节首拍'} · ${w.bars} 小节 · ${midDuck?'双窗口人声，中频 -5 dB':'无双窗口人声触发'} · ${prepared?'素材就绪':'需要准备素材'}`});viable=true
   }
  }
  if(!viable)reject(b,requireReady?'未就绪，或等待预算／能量方向／拍网格／窗口长度不满足':'等待预算／能量方向／拍网格／窗口长度不满足')
 }
 candidates.sort((x,y)=>y.score-x.score||x.end-y.end||x.id.localeCompare(y.id));return {best:candidates[0]||null,candidates,rejected}
}
export class RequestGate{
 revision=0;locked=false;deferred:Intent|null=null
 replace(intent:Intent){if(this.locked){this.deferred=intent;return null}return ++this.revision}
 isCurrent(token:number|null){return token!==null&&token===this.revision}
 reset(){this.revision++;this.locked=false;this.deferred=null}
}
