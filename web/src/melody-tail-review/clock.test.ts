import fs from 'node:fs'
import vm from 'node:vm'
import {expect,it} from 'vitest'
it('passes both PCM channels without a second gain, filter or limiter and observes exact frames',()=>{
 let Processor:any;const events:any[]=[],env:any={sampleRate:44100,currentFrame:0,Math,AudioWorkletProcessor:class{port={onmessage:null,postMessage:(x:any)=>events.push(x)}},registerProcessor:(_name:string,p:any)=>Processor=p};vm.runInNewContext(fs.readFileSync(new URL('../../public/review-clock.js',import.meta.url),'utf8'),env);const p=new Processor();p.port.onmessage({data:{kind:'arm',events:[{planId:'a',name:'takeover',frame:64}]}})
 const input=[Float32Array.from({length:128},(_,i)=>Math.sin(i)),Float32Array.from({length:128},(_,i)=>Math.cos(i))],out=[new Float32Array(128),new Float32Array(128)];p.process([input],[out]);expect(out[0]).toEqual(input[0]);expect(out[1]).toEqual(input[1]);expect(events[0]).toMatchObject({planId:'a',name:'takeover',frame:64,observedFrame:128,late:0})
})
