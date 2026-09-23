import {describe,it,expect} from 'vitest'
import {buildScene,sourceAtRenderTime} from './scene'
import type {Track,Plan} from '../realtime/planner'
const track=(id:string):Track=>({id,title:id,bpm:120,style:'Trap',styleScore:.2,duration:100,native:{url:id,sha256:id,bytes:1,duration:100},sections:[{start:0,end:20,label:'intro'},{start:20,end:60,label:'verse'}],bars:[0,2,4,6,8,10,12,14,16,18,20],vocals:[[8,12],[18,24]],energy:[],windows:[]})
const plan:Plan={id:'p',from:'a',to:'b',window:{id:'w',start:8,end:12,bars:1,role:'intro',energy:0,variants:{}},asset:{url:'head',sha256:'h',duration:2,rate:2,bytes:1},start:18,end:20,duration:2,restore:19,rate:2,score:1,midDuck:true,aVocal:1,bVocal:1,aEnergy:0,bEnergy:0,gridError:0,reason:'test',section:'verse',prepared:true}
describe('music transition scene',()=>{
 it('maps the stretched entry and native body to distinct source clocks',()=>{expect(sourceAtRenderTime(plan,'b',1)).toBe(10);expect(sourceAtRenderTime(plan,'b',3)).toBe(13);expect(sourceAtRenderTime(plan,'b',-.1)).toBeNull();expect(sourceAtRenderTime(plan,'a',2.1)).toBeNull()})
 it('clips vocals to the actually played lanes and calculates concurrent union overlap',()=>{const a=track('a'),b=track('b');a.vocals=[[17,19.5],[18,21]];b.vocals=[[8,12],[10,11],[14,16]];const s=buildScene(a,b,plan,0);expect(s.overlapSec).toBeCloseTo(2);expect(s.aVocals.every(x=>x.end<=2)).toBe(true);expect(s.bVocals.some(x=>x.start===4&&x.end===6)).toBe(true);expect(s.waitSec).toBe(20);expect(s.aCutInVocal).toBe(true)})
 it('keeps unknown vocal data distinct from silence and never mutates inputs',()=>{const a=track('a'),b=track('b');b.vocals=null;const before=JSON.stringify({a,b,plan});const s=buildScene(a,b,plan,5);expect(s.overlapSec).toBeNull();expect(JSON.stringify({a,b,plan})).toBe(before)})
 it('uses protection evidence as an acoustic candidate, not a human certification',()=>{const p={...plan,protection:{exit:{sectionEnd:19},automaticExit:{maxRmsDbfs:-35},entry:{lane:'original_silent'}}};const s=buildScene(track('a'),track('b'),p,0);expect(s.sectionTailSec).toBe(1);expect(s.protected).toBe(true);expect(s.certainty).toContain('声学候选')})
})

it('compares the section being faded, not the next section just after a near-boundary exit',()=>{const a=track('a');a.sections=[{start:0,end:10,label:'verse'},{start:10,end:20,label:'verse'},{start:20,end:60,label:'chorus'}];const p={...plan,start:18.1,end:20.1,duration:2};const s=buildScene(a,track('b'),p,0);expect(s.sectionEnd).toBe(20);expect(s.sectionTailSec).toBeCloseTo(.1);expect(s.exitSection).toBe('verse')})
