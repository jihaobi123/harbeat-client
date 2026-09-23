import {it,expect} from 'vitest'
import {guardPlan,mergeSections,mappedOverlap,type GuardCatalog,type Reviews} from './planner'
const asset=(id:string,duration=120)=>({url:id,sha256:id,duration,bytes:1})
const track=(id:string):any=>({id,title:id,bpm:120,duration:120,style:'x',styleScore:0,native:asset(id),bars:Array.from({length:61},(_,i)=>i*2),sections:[{start:0,end:24,label:'verse'}],vocals:[[0,22]],energy:[{start:0,end:120,value:.5}],windows:[{id:'intro',start:0,end:8,bars:4,role:'intro',energy:.5,variants:{a:{...asset('entry',8),rate:1}}}],provenance:{masterSha256:id}})
function fixture(){const a=track('a'),b=track('b');b.vocals=[[10,20]];return {tracks:[a,b],evidence:{a:{exits:[{id:'exit',cut:24,sectionEnd:24,start:0,label:'verse'}],windows:{}},b:{exits:[],windows:{intro:{start:0,end:8,sectionStart:0,sectionEnd:12,lane:'instrumental',sourceHashes:['s1','s2','s3']}}}}} as unknown as GuardCatalog}
it('fails closed without exact listened evidence and merges adjacent same-label blocks',()=>{
 expect(mergeSections([{start:0,end:8,label:'chorus'},{start:8,end:16,label:'chorus'}])).toEqual([{start:0,end:16,label:'chorus'}]);const c=fixture();expect(guardPlan(c,{},c.tracks[0],c.tracks,2,{kind:'next'},new Set(),18,false).best).toBeNull()
})
it('does not convert marginal scores or longer waiting into approvals',()=>{const c=fixture();for(const budget of [18,120]){const r=guardPlan(c,{},c.tracks[0],c.tracks,2,{kind:'next'},new Set(),budget,false);expect(r.best).toBeNull();expect(r.exclusions.some(x=>x.code==='exit_unreviewed')).toBe(true)}})
it('requires matching source/entry hashes and respects containment',()=>{const c=fixture();const reviews:Reviews={exits:{'a:exit':{masterSha256:'a',cut:24,confirmedAt:'test',phraseEnded:true}},entries:{'b:intro:a':{assetSha256:'entry',bodySha256:'b',confirmedAt:'test',noVocalEntry:true,bodyStartsClean:true}}};
 const ok=guardPlan(c,reviews,c.tracks[0],c.tracks,2,{kind:'next'},new Set(['a','b','entry']),120);expect(ok.best?.end).toBe(24);expect(ok.best?.midDuck).toBe(false)
 reviews.entries!['b:intro:a'].assetSha256='stale';expect(guardPlan(c,reviews,c.tracks[0],c.tracks,2,{kind:'next'},new Set(),120,false).best).toBeNull();reviews.entries!['b:intro:a'].assetSha256='entry';c.evidence.b.windows.intro.sectionEnd=6;expect(guardPlan(c,reviews,c.tracks[0],c.tracks,2,{kind:'next'},new Set(),120,false).best).toBeNull()
})
it('maps actual intervals into shared time rather than multiplying occupancy',()=>{expect(mappedOverlap([[0,2]],[[2,4]],0,0,1,4)).toBe(0);expect(mappedOverlap([[1,3]],[[2,6]],0,0,2,4)).toBe(2)})
function approved():Reviews{return {exits:{'a:exit':{masterSha256:'a',cut:24,confirmedAt:'test',phraseEnded:true}},entries:{'b:intro:a':{assetSha256:'entry',bodySha256:'b',confirmedAt:'test',noVocalEntry:true,bodyStartsClean:true}}}}
it('rejects exact-source changes, body mid-phrase rejection, missing vocals and unready assets',()=>{
 for(const change of [(c:GuardCatalog,r:Reviews)=>{r.exits!['a:exit'].phraseEnded=false},(c:GuardCatalog,r:Reviews)=>{r.entries!['b:intro:a'].bodyStartsClean=false},(c:GuardCatalog)=>{c.tracks[0].provenance!.masterSha256='changed'},(c:GuardCatalog)=>{c.tracks[1].native.sha256='changed'},(c:GuardCatalog)=>{c.tracks[0].vocals=null}]){const c=fixture(),r=approved();change(c,r);expect(guardPlan(c,r,c.tracks[0],c.tracks,2,{kind:'next'},new Set(),120,false).best).toBeNull()}
 const c=fixture();expect(guardPlan(c,approved(),c.tracks[0],c.tracks,2,{kind:'next'},new Set(),120).best).toBeNull()
})
it('blocks budget deadline and bad grid without weakening protection; reviewed detector disagreement is retained',()=>{
 const c=fixture(),r=approved();expect(guardPlan(c,r,c.tracks[0],c.tracks,2,{kind:'next'},new Set(),18,false).best).toBeNull();c.tracks[0].vocals=[[0,40]];const plan=guardPlan(c,r,c.tracks[0],c.tracks,2,{kind:'next'},new Set(),120,false).best as any;expect(plan.protection.detectorActiveAtExit).toBe(true);expect(plan.protection.exitReview).toEqual(r.exits!['a:exit']);c.tracks[0].bars=[0,2];expect(guardPlan(c,r,c.tracks[0],c.tracks,2,{kind:'next'},new Set(),120,false).best).toBeNull()
})
