import {expect,it} from 'vitest'
import {reviewWindow,extractReview} from './render'
it('extracts four seconds before and three after the unchanged takeover, including original limiter delay',()=>{
 const w=reviewWindow(4,9.151564625850341,8,44100)
 expect(w.frames).toBe(7*44100);expect(w.takeoverFrame).toBe(4*44100)
 expect(w.startFrame).toBe(Math.round((.1+4+9.151564625850341)*44100)+221-4*44100)
})
it('keeps all inner samples unchanged and applies only five millisecond excerpt edges',()=>{
 const source=new Float32Array(2000).fill(.25),out=extractReview([source,source],100,1000)
 expect(out[0].length).toBe(1000);expect(out[0][0]).toBe(0);expect(out[0][500]).toBe(.25);expect(out[0].at(-1)).toBe(0);expect(source[100]).toBe(.25)
})
it('rejects impossible windows, incomplete channels and nonfinite PCM',()=>{
 expect(()=>reviewWindow(4,2,2)).toThrow();expect(()=>reviewWindow(NaN,8,8)).toThrow()
 expect(()=>extractReview([new Float32Array(10),new Float32Array(9)],0,10)).toThrow()
 expect(()=>extractReview([new Float32Array([NaN]),new Float32Array(1)],0,1)).toThrow()
})
