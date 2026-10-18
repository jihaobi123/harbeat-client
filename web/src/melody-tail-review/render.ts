import type {MelodyYieldCase} from '../melody-yield/transport'
import type {Mode} from '../melody-yield/policy'
import {makeYieldGraph} from '../melody-yield/graph'
export function reviewWindow(pre:number,duration:number,post:number,sampleRate=44100){
 if(![pre,duration,post,sampleRate].every(Number.isFinite)||pre<0||duration<=0||pre+duration<4||post<3||sampleRate!==44100)throw Error('末尾补听范围不完整')
 const delayFrames=Math.ceil(sampleRate*.005),takeoverFrame=4*sampleRate,startFrame=Math.round((.1+pre+duration)*sampleRate)+delayFrames-takeoverFrame
 return {startFrame,frames:7*sampleRate,takeoverFrame,delayFrames,sampleRate}
}
export function extractReview(channels:Float32Array[],start:number,length:number):Float32Array[]{
 if(channels.length!==2||![start,length].every(Number.isInteger)||start<0||length<1||channels.some(c=>c.length<start+length||c.length!==channels[0].length))throw Error('补听音频不完整')
 const edge=Math.min(221,Math.floor(length/2)),result=channels.map(c=>c.slice(start,start+length))
 for(const x of result){for(let i=0;i<x.length;i++)if(!Number.isFinite(x[i]))throw Error('补听音频包含无效采样');for(let i=0;i<edge;i++){x[i]*=i/edge;x[x.length-1-i]*=i/edge}}
 return result
}
async function pcmSha(channels:Float32Array[]){
 const data=new ArrayBuffer(channels[0].length*8),view=new DataView(data)
 for(let i=0;i<channels[0].length;i++)for(let c=0;c<2;c++)view.setFloat32((i*2+c)*4,channels[c][i],true)
 return [...new Uint8Array(await crypto.subtle.digest('SHA-256',data))].map(x=>x.toString(16).padStart(2,'0')).join('')
}
export async function renderTail(c:MelodyYieldCase,mode:Mode,decoded:Record<string,AudioBuffer>,base:URL){
 const sampleRate=44100,window=reviewWindow(c.pre,c.plan.duration,c.post),total=c.pre+c.plan.duration+c.post
 const ctx=new OfflineAudioContext(2,Math.ceil((.1+total+.1)*sampleRate),sampleRate)
 await ctx.audioWorklet.addModule(new URL('vocal-echo-clock.js',base))
 const monitor=new AudioWorkletNode(ctx,'vocal-echo-clock',{outputChannelCount:[2]}),output=ctx.createGain(),observations:any[]=[]
 output.gain.value=.7;monitor.connect(output);output.connect(ctx.destination);monitor.port.onmessage=({data})=>observations.push(data)
 makeYieldGraph(ctx,monitor,decoded,c,mode,.1)
 const markers=[{t:0,name:'试听开始'},{t:c.pre+c.yieldEnd,name:'旋律收完'},{t:c.pre+c.plan.duration,name:'原接管'},{t:total,name:'完整计划结束'}]
 monitor.port.postMessage({kind:'arm',events:markers.map(x=>({planId:'offline',name:x.name,frame:Math.round((.1+x.t)*sampleRate)}))})
 const full=await ctx.startRendering();await new Promise(resolve=>setTimeout(resolve,0))
 if(!observations.some(x=>x.name==='原接管'&&x.late===0&&x.limiterDelayFrames===window.delayFrames))throw Error('完整原计划的接管渲染未核验')
 const fullChannels=[full.getChannelData(0),full.getChannelData(1)],channels=extractReview(fullChannels,window.startFrame,window.frames)
 const buffer=ctx.createBuffer(2,window.frames,sampleRate);channels.forEach((x,i)=>buffer.getChannelData(i).set(x))
 const receipt={window,fullFrames:full.length,fullPcmSha256:await pcmSha(fullChannels),excerptPcmSha256:await pcmSha(channels),observations,fullPlanSha256:c.planSha256,mode,assets:c.assets,outputGain:.7,excerptEdgeFrames:221,graph:'shared makeYieldGraph; original EQ/master/other gains and native handoff; full render before crop'}
 monitor.disconnect();output.disconnect();return {buffer,receipt}
}
