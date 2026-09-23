import {it,expect} from 'vitest'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
it('audio thread limits actual PCM, delays five milliseconds and reports quantum observations',()=>{
 let Processor:any;const messages:any[]=[];const sandbox:any={sampleRate:44100,currentFrame:0,Float32Array,Float64Array,Math,AudioWorkletProcessor:class{port={onmessage:null,postMessage:(v:any)=>messages.push(v)}},registerProcessor:(_name:string,p:any)=>{Processor=p}}
 vm.runInNewContext(readFileSync(new URL('../../public/v3-clock.js',import.meta.url),'utf8'),sandbox)
 const processor=new Processor();processor.port.onmessage({data:{kind:'arm',events:[{planId:'x',name:'start',frame:441}]}})
 const output:number[]=[]
 for(let block=0;block<30;block++){const input=Float32Array.from({length:128},(_,j)=>Math.sin((block*128+j)*2*Math.PI*997/44100)*1.7);const channels=[new Float32Array(128),new Float32Array(128)];sandbox.currentFrame=block*128;processor.process([[input,input]],[channels]);output.push(...channels[0])}
 expect(output.every(Number.isFinite)).toBe(true);expect(Math.max(...output.map(Math.abs))).toBeLessThanOrEqual(.96001);expect(output.slice(0,221).every(x=>x===0)).toBe(true)
 expect(messages).toHaveLength(1);expect(messages[0].observedFrame).toBe(512);expect(messages[0].frame).toBe(441);expect(messages[0].limiterDelayFrames).toBe(221);expect(messages[0].limiterGainAtObservation).toBeLessThan(1);expect(messages[0].sessionMinimumLimiterGain).toBeLessThanOrEqual(messages[0].limiterGainAtObservation);expect(messages[0].sessionMinimumLimiterGain).toBeGreaterThan(0)
 processor.port.onmessage({data:{kind:'arm',events:[{planId:'cancelled',name:'event',frame:4000}]}});processor.port.onmessage({data:{kind:'cancel',planId:'cancelled'}});sandbox.currentFrame=4096;processor.process([[new Float32Array(128)]],[[new Float32Array(128),new Float32Array(128)]]);expect(messages).toHaveLength(1)
})
