import {expect,it} from 'vitest'
import {treatment,validateRelay} from './policy'
import {bassCurves} from '../bass-swap/policy'
const timing={duckStart:2,swapStart:3.5,swapEnd:4}
const relay={aVoiceEnd:16,bEntry:20,bEnd:28,aIntervals:[[10,16]],bIntervals:[]}
it('keeps original bass and reproduces the original full-track fade in reference',()=>{
 const p=treatment(4,8,timing,'stem','natural',6)
 expect(p.bass).toEqual(bassCurves(4,8,timing,'swap'))
 expect(p.a.bed).toEqual(p.bass.a.rest);expect(p.a.voice).toEqual(p.a.bed)
 expect(p.b.bed).toEqual(p.bass.b.rest);expect(p.b.voice).toEqual(p.b.bed)
})
it('hands over accompaniment earlier while preserving A voice and original B voice/bass',()=>{
 const p=treatment(4,8,timing,'stem','relay',6)
 expect(p.a.bed).toEqual([[0,1],[4,1],[7.2,0],[12,0]])
 expect(p.a.voice).toEqual([[0,1],[10.15,1],[12,0]])
 expect(p.b.voice).toEqual(p.bass.b.rest)
 expect(p.b.bed).toEqual([[0,0],[4,0],[7.2,1],[12,1]])
 expect(p.bass).toEqual(bassCurves(4,8,timing,'swap'))
})
it('requires detected A ending inside original window and an entirely guarded empty B entry',()=>{
 expect(()=>validateRelay(10,18,8,relay)).not.toThrow()
 expect(()=>validateRelay(10,18,8,{...relay,aVoiceEnd:18,aIntervals:[[10,18]]})).toThrow()
 expect(()=>validateRelay(10,18,8,{...relay,bIntervals:[[27.9,29]]})).toThrow()
 expect(()=>validateRelay(10,18,8,{...relay,aVoiceEnd:15})).toThrow()
 expect(()=>validateRelay(10,18,8,{...relay,aIntervals:[[15.5,16]]})).toThrow()
})
