import {describe,it,expect} from 'vitest'
import {createRound,markHeard,markPlayed,recordChoice,revealCase,setPractice,archiveRound,updateFeedback,canVote,withPlayerLogs,restoreStore,type RoundStore} from './rounds'

const ids=['a','b','c']
const make=(id='round-1',phase:0|1=0)=>createRound(ids,'selection',false,()=>.23,'2026-10-18T01:00:00Z',id,phase)
const hear=(r=make(),letter:'A'|'B'='A')=>markHeard(r,{roundId:r.id,caseId:'a',letter,status:'complete'},`heard-${letter}`)
const store=(current=make()):RoundStore=>({schema:'harbeat.vocal-echo-rounds.v1',current,history:[],playerLogs:[]})

describe('vocal bed blind rounds',()=>{
 it('supports two or three cases with independent assignments, including identical orientations',()=>{
  const r=make()
  expect(Object.values(r.cases).every(c=>c.mapping.A==='natural'&&c.mapping.B==='relay')).toBe(true)
  expect(Object.keys(createRound(['a','b'],'s').cases)).toHaveLength(2)
  expect(()=>createRound([],'s')).toThrow()
  expect(()=>createRound(['a','b','c','d'],'s')).toThrow()
  expect(()=>createRound(['a','a'],'s')).toThrow()
 })
 it('alternates recommended first letters and flips the next round independently of mappings',()=>{
  expect(Object.values(make().cases).map(c=>c.recommendedOrder)).toEqual([['A','B'],['B','A'],['A','B']])
  expect(Object.values(make('next',1).cases).map(c=>c.recommendedOrder)).toEqual([['B','A'],['A','B'],['B','A']])
  expect(make('next',1).cases.a.mapping).toEqual(make().cases.a.mapping)
 })
 it('records actual first playback rather than assuming the recommendation was followed',()=>{
  const r=markPlayed(make(),{roundId:'round-1',caseId:'a',letter:'B',status:'playing'},'actual')
  expect(r.cases.a.firstPlayed).toEqual({letter:'B',at:'actual'})
  expect(markPlayed(r,{roundId:r.id,caseId:'a',letter:'A',status:'playing'},'later').cases.a.firstPlayed).toEqual(r.cases.a.firstPlayed)
  for(const status of ['loading','idle','complete'])expect(markPlayed(make(),{roundId:'round-1',caseId:'a',letter:'A',status},'bad').cases.a.firstPlayed).toBeUndefined()
 })
 it('accepts immediate preferences and freezes each heard snapshot independently',()=>{
  const first=recordChoice(make(),'a','B','first')
  expect(canVote(first,'a')).toBe(true)
  expect(canVote(first,'missing')).toBe(false)
  expect(first.cases.a.firstBlindChoice).toEqual({choice:'B',at:'first',heard:{}})
  const edited=recordChoice(hear(first),'a','A','edit')
  expect(edited.cases.a.firstBlindChoice).toEqual(first.cases.a.firstBlindChoice)
  expect(edited.cases.a.votes[1]).toEqual({choice:'A',at:'edit',afterReveal:false,heard:{A:'heard-A'}})
 })
 it('ignores incomplete or stale completion callbacks and unknown case or letters',()=>{
  const r=make()
  for(const event of [{roundId:'old',caseId:'a',letter:'A',status:'complete'},{roundId:r.id,caseId:'a',letter:'A',status:'idle'},{roundId:r.id,caseId:'a',letter:'C',status:'complete'},{roundId:r.id,caseId:'missing',letter:'A',status:'complete'}])expect(markHeard(r,event)).toBe(r)
  expect(hear(r).cases.a.heard).toEqual({A:'heard-A'})
 })
 it('requires every first formal choice before reveal but never requires full playback',()=>{
  let r=recordChoice(recordChoice(make(),'a','tie'),'b','A')
  expect(revealCase(r,'a')).toBe(r)
  r=recordChoice(r,'c','none')
  expect(revealCase(r,'a','allowed').cases.a.revealedAt).toBe('allowed')
 })
 it('allows practice reveals and locks practice classification after choice or playback',()=>{
  const chosen=recordChoice(setPractice(make(),true),'a','A','first')
  const revealed=revealCase(chosen,'a','revealed')
  expect(recordChoice(revealed,'a','B','later').cases.a.votes[1].afterReveal).toBe(true)
  expect(revealCase(revealed,'a','later').cases.a.revealedAt).toBe('revealed')
  expect(setPractice(chosen,false)).toBe(chosen)
  const started={...make(),startedAt:'start'}
  expect(setPractice(started,true)).toBe(started)
 })
 it('preserves archived feedback and playback logs on a fresh inverted round',()=>{
  const old=updateFeedback(recordChoice(hear(),'a','A'),'a',['voice-cut'],'B 重复明显')
  const saved=withPlayerLogs(withPlayerLogs(store(old),'one',[1]),'one',[1,2])
  const next=archiveRound(saved,make('next',1))
  expect(next.history).toEqual([old]);expect(next.playerLogs).toEqual([{sessionId:'one',logs:[1,2]}])
  expect(next.current.cases.a.firstBlindChoice).toBeUndefined()
 })
 it('restores mappings, actual playback and heard snapshots with no balance assumption',()=>{
  const saved=store(recordChoice(markPlayed(hear(),{roundId:'round-1',caseId:'a',letter:'B',status:'playing'},'played'),'a','A','choice'))
  expect(restoreStore(JSON.stringify(saved),make('new'))).toEqual(saved)
  expect(restoreStore(null,make())).toEqual(store())
 })
 it('rejects malformed mappings, order, snapshots, phase and logs without overwriting',()=>{
  const mutations=[(s:RoundStore)=>{s.current.cases.a.mapping.B='natural'},(s:RoundStore)=>{s.current.cases.a.recommendedOrder=['B','A']},(s:RoundStore)=>{Object.assign(s.current,{orderPhase:2})},(s:RoundStore)=>{Object.assign(s.current.cases.a,{firstBlindChoice:{choice:'C',at:'now',heard:{}}})},(s:RoundStore)=>{Object.assign(s.current.cases.a,{firstPlayed:{letter:'C',at:'now'}})},(s:RoundStore)=>{Object.assign(s,{playerLogs:[{sessionId:'x'}]})}]
  for(const mutate of mutations){const saved=store();mutate(saved);expect(()=>restoreStore(JSON.stringify(saved),make())).toThrow('本机记录')}
 })
 it('archives old source evidence on a pack change and rejects different IDs on the same pack',()=>{
  const old={...make(),sourceSnapshot:{old:true}},fresh={...make('next'),selectionSha256:'new'}
  expect(restoreStore(JSON.stringify(store(old)),fresh).history).toEqual([old])
  expect(()=>restoreStore(JSON.stringify(store()),createRound(['x','y','z'],'selection'))).toThrow('本机记录')
 })
})

it("supports a single eligible pair without inventing a second example",()=>{const r=createRound(["one"],"hash");expect(Object.keys(r.cases)).toEqual(["one"]);expect(recordChoice(r,"one","tie").cases.one.firstBlindChoice?.heard).toEqual({})})

it("archives same-selection rounds if rendered audio assets change",()=>{const old={...make(),assetFingerprint:"old"},fresh={...make("new"),assetFingerprint:"new"};const restored=restoreStore(JSON.stringify(store(old)),fresh);expect(restored.history).toEqual([old]);expect(restored.current.id).toBe("new")})
