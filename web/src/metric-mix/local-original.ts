import type {Track,Plan,Asset} from '../realtime/planner'
import {nativeSegments,nativeSegment} from '../continuous/segments'
import {scheduleV30Eq} from '../v30/eq'
import {localBeatGate} from '../continuous/beatAlignment'
import {requireBoundVocals} from '../vocal-overlap/planner'
import type {MetricTransport} from './transport'
import type {Prepared,Method} from './types'
export const LOCAL_ORIGINAL='browser-v3-original-v1'
/** Original verified PCM, existing stretched entry, and eight native B tail ms. */
export function originalInputs(a:Track,b:Track,plan:Plan){
 requireBoundVocals(a);requireBoundVocals(b)
 if(plan.from!==a.id||plan.to!==b.id||!plan.v30Eq||plan.start<0||plan.end>a.duration||plan.rate<.95||plan.rate>1.05||plan.window.end+.008>b.duration)throw Error('原渐混的来源或接点不一致')
 const timing=localBeatGate(a,b,{start:plan.start,end:plan.end,window:plan.window,rate:plan.rate,duration:plan.duration});if(timing)throw Error(timing)
 const rows=(t:Track,start:number)=>{const first=t.alignment!.bars.findIndex(r=>Math.abs(r.start-start)<=.065);return t.alignment!.bars.slice(first,first+plan.window.bars)}
 const aa=rows(a,plan.start),bb=rows(b,plan.window.start),beats=(rows:typeof aa)=>[...rows.flatMap(r=>r.beats),rows.at(-1)!.end]
 const from=beats(aa),to=beats(bb),beatErrorMs=Math.max(...from.map((t,i)=>Math.abs(t-(plan.start+(to[i]-plan.window.start)/plan.rate))))*1000
 const outgoing=nativeSegments(a).filter(s=>s.end>plan.start&&s.start<plan.end)
 if(!outgoing.length||outgoing[0].start>plan.start+.0001||outgoing.at(-1)!.end<plan.end-.0001)throw Error('原曲片段未覆盖接点')
 return {outgoing,entry:plan.asset,body:nativeSegment(b,plan.window.end),nativeTail:nativeSegments(b).filter(s=>s.end>plan.window.end&&s.start<plan.window.end+.008),beatErrorMs}
}
export async function preloadOriginal(p:MetricTransport,a:Track,b:Track,plan:Plan,signal:AbortSignal){
 const inputs=originalInputs(a,b,plan),assets=[...inputs.outgoing.map(s=>s.asset),inputs.entry,...inputs.nativeTail.map(s=>s.asset)]
 await Promise.all([...new Map(assets.map(asset=>[asset.url,asset])).values()].map(asset=>p.cache.load(asset,signal)))
 return inputs
}
function wave(buffer:AudioBuffer){
 const frames=buffer.length,bytes=new ArrayBuffer(44+frames*8),v=new DataView(bytes),text=(at:number,s:string)=>{for(let i=0;i<s.length;i++)v.setUint8(at+i,s.charCodeAt(i))}
 text(0,'RIFF');v.setUint32(4,bytes.byteLength-8,true);text(8,'WAVE');text(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,3,true);v.setUint16(22,2,true);v.setUint32(24,buffer.sampleRate,true);v.setUint32(28,buffer.sampleRate*8,true);v.setUint16(32,8,true);v.setUint16(34,32,true);text(36,'data');v.setUint32(40,frames*8,true)
 const l=buffer.getChannelData(0),r=buffer.getChannelData(1)
 for(let i=0;i<frames;i++){if(!Number.isFinite(l[i])||!Number.isFinite(r[i]))throw Error('混音输出无效');v.setFloat32(44+i*8,l[i],true);v.setFloat32(48+i*8,r[i],true)}
 return bytes
}
/** Reuse the established browser V3 gains, EQ frequencies, wet/dry ramps and
 * source positions. No new stem effect or remote render is introduced. */
export async function localOriginal(p:MetricTransport,a:Track,b:Track,plan:Plan,signal:AbortSignal):Promise<Prepared>{
 const inputs=await preloadOriginal(p,a,b,plan,signal);signal.throwIfAborted()
 const sr=p.ctx.sampleRate,d=plan.duration,ctx=new OfflineAudioContext(2,Math.round((d+.008)*sr),sr)
 const graph=(side:'a'|'b')=>{
  const input=ctx.createGain(),low=ctx.createBiquadFilter(),high=ctx.createBiquadFilter(),mid=ctx.createBiquadFilter(),wet=ctx.createGain(),dry=ctx.createGain(),gain=ctx.createGain()
  low.type='lowshelf';low.frequency.value=140;high.type='highshelf';high.frequency.value=3600;mid.type='peaking';mid.frequency.value=1200;mid.Q.value=1.05
  input.connect(low);low.connect(high);high.connect(mid);mid.connect(wet);input.connect(dry);wet.connect(gain);dry.connect(gain);gain.connect(ctx.destination)
  const restore=d-Math.min(d,120/a.bpm)
  gain.gain.setValueAtTime(side==='a'?.60:0,0);gain.gain.linearRampToValueAtTime(side==='a'?0:.60,d)
  if(side==='a'){wet.gain.setValueAtTime(0,0);wet.gain.linearRampToValueAtTime(1,.02);dry.gain.setValueAtTime(1,0);dry.gain.linearRampToValueAtTime(0,.02)}
  else{wet.gain.setValueAtTime(1,0);wet.gain.setValueAtTime(1,restore);wet.gain.linearRampToValueAtTime(0,d);dry.gain.setValueAtTime(0,0);dry.gain.setValueAtTime(0,restore);dry.gain.linearRampToValueAtTime(1,d)}
  return {input,low,high,mid}
 }
 const ga=graph('a'),gb=graph('b');scheduleV30Eq(ga,gb,0,plan.v30Eq!)
 const buffer=(asset:Asset)=>{const value=p.cache.buffers.get(asset.url);if(!value)throw Error('交接素材尚未就绪');return value}
 const source=(pcm:AudioBuffer,target:AudioNode,at:number,offset:number,length:number)=>{const node=ctx.createBufferSource();node.buffer=pcm;node.connect(target);node.start(at,offset,length)}
 for(const segment of inputs.outgoing){const s=Math.max(plan.start,segment.start),e=Math.min(plan.end,segment.end);source(buffer(segment.asset),ga.input,s-plan.start,s-segment.start,e-s)}
 source(buffer(inputs.entry),gb.input,0,0,d)
 const tail=ctx.createGain();tail.gain.value=.60;tail.connect(ctx.destination);for(const segment of inputs.nativeTail){const s=Math.max(plan.window.end,segment.start),e=Math.min(plan.window.end+.008,segment.end);source(buffer(segment.asset),tail,d+s-plan.window.end,s-segment.start,e-s)}
 const rendered=await ctx.startRendering();signal.throwIfAborted()
 const asset=await p.cache.localWav(wave(rendered),rendered.duration,signal);signal.throwIfAborted()
 let peak=0;for(let c=0;c<2;c++)for(const x of rendered.getChannelData(c))peak=Math.max(peak,Math.abs(x))
 const names={original:'原渐混（就近接歌）',bass:'独立贝斯交接',filter:'旋律滤波',yield:'旋律让位',vocal:'人声唱完再退出',bass_filter:'贝斯交接＋旋律滤波'}
 const methods=Object.fromEntries(Object.entries(names).map(([key,name])=>[key,{name,eligible:key==='original',score:key==='original'?50:null,reason:key==='original'?'最近合格接点采用原有浏览器渐混；该接点的分轨方案尚未就绪':'本次未等待云端生成此接点的分轨方案',processingCost:0,levelPenalty:0}])) as Prepared['decision']['methods']
 return {schema:'harbeat.metric-mix-result.v1',id:asset.sha256,status:'ready',policyVersion:LOCAL_ORIGINAL,codeVersion:LOCAL_ORIGINAL,
  plan:{from:a.id,to:b.id,windowId:plan.window.id,start:plan.start,end:plan.end,duration:d,rate:plan.rate,bStart:plan.window.start,bEnd:plan.window.end,beatErrorMs:inputs.beatErrorMs},
  metrics:{bassOverlap:null,otherOverlap:null,bassDifference:null,otherDifference:null,vocalSafe:false,vocalBenefit:0,definitions:{status:'本地原渐混；保留原有选点的人声检查，未计算本接点的分轨指标'}},
  decision:{recommended:'original',explanation:methods.original.reason,policy:{version:LOCAL_ORIGINAL},limitations:['这是已验证素材的浏览器原渐混，不是云端分轨效果判断'],methods},assets:{original:asset},stats:{peak},
  sourceProof:{rendering:LOCAL_ORIGINAL,from:a.provenance,to:b.provenance,entry:inputs.entry,aSegments:inputs.outgoing.map(s=>s.asset),body:inputs.body.asset,eq:plan.v30Eq}}
}
