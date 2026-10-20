import {makeCombinationGraph} from '../combination-step-one/graph'
import {makeFilterGraph} from '../melody-filter/graph'
import {makeLegacyBassReference} from '../combination-step-one/legacy-reference'
import type {CombinationCase} from '../combination-step-one/transport'
const button=document.querySelector('button')!,status=document.querySelector('pre')!
button.onclick=async()=>{
 button.disabled=true
 try{
  status.textContent='正在核验十二个素材指纹与真实离线音频…'
  const pack=await fetch('./combination-single-control-data.json').then(r=>r.json()),reports:any[]=[]
  for(const c of pack.cases as CombinationCase[]){
  const sr=44100,at=1,total=c.pre+c.plan.duration+c.post,n=Math.ceil((at+total+.1)*sr)
  const decoder=new OfflineAudioContext(2,1,sr),decoded:Record<string,AudioBuffer>={}
  for(const [key,a] of Object.entries(c.assets)){
   const raw=await fetch(a.url).then(r=>{if(!r.ok)throw Error('素材读取失败');return r.arrayBuffer()})
   const sha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(x=>x.toString(16).padStart(2,'0')).join('')
   if(sha!==a.sha256)throw Error('素材指纹改变：'+key)
   decoded[key]=await decoder.decodeAudioData(raw)
  }
  decoded.bEntryOther=decoder.createBuffer(2,Math.round(c.plan.duration*sr),sr);decoded.bBodyOther=decoder.createBuffer(2,Math.round(c.post*sr),sr);decoded.bBodyBass=decoded.bBodyOther
  async function render(mode:'original'|'single'|'combined'|'plain-reference'|'filter-reference'|'bass-reference'|'previous-combined'){
   const ctx=new OfflineAudioContext(2,n,sr)
   if(mode==='plain-reference'||mode==='filter-reference')makeFilterGraph(ctx,ctx.destination,decoded,c,mode==='plain-reference'?'natural':'relay',at)
   else if(mode==='bass-reference')makeLegacyBassReference(ctx,ctx.destination,decoded,c,at)
   else if(mode==='previous-combined')makeCombinationGraph(ctx,ctx.destination,decoded,{...c,singleTechnique:'bass'},'combined',at)
   else makeCombinationGraph(ctx,ctx.destination,decoded,c,mode,at)
   const out=await ctx.startRendering();return [out.getChannelData(0),out.getChannelData(1)]
  }
  const outputs:Record<string,Float32Array[]>={}
  for(const mode of ['original','single','combined','plain-reference','filter-reference','bass-reference','previous-combined'] as const){status.textContent='正在渲染：'+mode;outputs[mode]=await render(mode)}
  function maxDiff(a:Float32Array[],b:Float32Array[],start=0,end=n){let m=0;for(let ch=0;ch<2;ch++)for(let i=start;i<end;i++)m=Math.max(m,Math.abs(a[ch][i]-b[ch][i]));return m}
  let deltaError=0
  for(let ch=0;ch<2;ch++)for(let i=0;i<n;i++)deltaError=Math.max(deltaError,Math.abs((outputs.combined[ch][i]-outputs.single[ch][i])-(outputs['bass-reference'][ch][i]-outputs['plain-reference'][ch][i])))
  const measures={originalVsLegacyPlain:maxDiff(outputs.original,outputs['plain-reference']),singleVsFilterOnly:maxDiff(outputs.single,outputs['filter-reference']),combinedVsPreviousCombined:maxDiff(outputs.combined,outputs['previous-combined']),addedDifferenceVsOnlyBass:deltaError,beforeBassOriginalVsCombined:maxDiff(outputs.single,outputs.combined,0,Math.floor((at+c.pre)*sr)),postHandoffAllSame:maxDiff(outputs.original,outputs.combined,Math.ceil((at+c.pre+c.plan.duration)*sr)),originalVsSingle:maxDiff(outputs.original,outputs.single),singleVsCombined:maxDiff(outputs.single,outputs.combined)}
  const stats=Object.fromEntries(Object.entries(outputs).map(([k,channels])=>{let peak=0,power=0;for(const x of channels)for(const v of x){peak=Math.max(peak,Math.abs(v));power+=v*v}return [k,{peak,rms:Math.sqrt(power/(n*2))}]}))
  const pass=measures.originalVsLegacyPlain<2e-6&&measures.singleVsFilterOnly<2e-6&&measures.combinedVsPreviousCombined<2e-6&&measures.addedDifferenceVsOnlyBass<2e-6&&measures.beforeBassOriginalVsCombined<2e-6&&measures.postHandoffAllSame<2e-6&&measures.originalVsSingle>1e-4&&measures.singleVsCombined>1e-4
  const report={caseId:c.id,aTitle:c.aTitle,bTitle:c.bTitle,schema:'harbeat.combination-offline-audit.v1',selectionSha256:pack.selectionSha256,sampleRate:sr,frames:n,at,total,pass,measures,stats,scope:'Real OfflineAudioContext, pre-limiter graph; equal0.60headroom; no perceived loudness matching or subjective judgement.'}
  reports.push(report)
  }
  const report={schema:'harbeat.combination-single-control-offline-audit.v1',selectionSha256:pack.selectionSha256,pass:reports.every(x=>x.pass),reports}
  status.textContent=JSON.stringify(report,null,2)
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));a.download='HarBeat-滤波单项参照-离线音频核验.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)
 }catch(e){status.textContent='核验失败：'+(e as Error).message}finally{button.disabled=false}
}
