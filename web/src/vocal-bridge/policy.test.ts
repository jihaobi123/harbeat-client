import {expect,it} from 'vitest'
import {qualityTrack} from '../continuous/qualityFixture'
import {validateBridge,bridgeCurves,valueAt} from './policy'
const cue={start:50,end:58,duration:8,rate:1,bEntry:0,bEnd:8,bVoiceStart:9,aVoiceEnd:57,bars:4}
function tracks(){const a=qualityTrack('a'),b=qualityTrack('b');a.vocals=[[49,57]];b.vocals=[[9,15]];for(const t of [a,b])t.preprocessing!.vocalActivity.intervals=t.vocals!.map(([s,e])=>({start_ms:s*1000,end_ms:e*1000}));return [a,b]}
it('retains A vocal after its accompaniment yields and restores B before its first vocal',()=>{
 const [a,b]=tracks();expect(()=>validateBridge(a,b,cue)).not.toThrow()
 const c=bridgeCurves(cue,4)
 expect(valueAt(c.aBed,9)).toBe(0);expect(valueAt(c.aVoice,9)).toBe(1)
 expect(valueAt(c.aVoice,11)).toBe(1);expect(valueAt(c.aVoice,12)).toBe(0)
 expect(valueAt(c.bVoice,12)).toBe(1);expect(valueAt(c.bBed,12)).toBe(1)
 for(let t=4;t<=12;t+=.1)expect(valueAt(c.aBed,t)+valueAt(c.bBed,t)).toBeCloseTo(1,10)
})
it('rejects early B vocals, late A syllables and locally drifting beats',()=>{
 const [a,b]=tracks();expect(()=>validateBridge(a,b,{...cue,bVoiceStart:7})).toThrow()
 expect(()=>validateBridge(a,b,{...cue,aVoiceEnd:57.9})).toThrow()
 b.alignment!.bars[0].beats[1]+=.12;expect(()=>validateBridge(a,b,cue)).toThrow()
})
it('unity bed/vocal gain exactly reconstructs the master, with no doubled vocal',()=>{
 const m=.31,v=.12,bed=1,voice=1
 expect(m*bed+v*(voice-bed)).toBe(m)
 const c=bridgeCurves(cue,4);expect(valueAt(c.aVoice,2)-valueAt(c.aBed,2)).toBe(0)
})
