import {describe,it,expect} from 'vitest'
import {createRound,markHeard,recordChoice,revealCase,setPractice,archiveRound,updateFeedback,canVote,withPlayerLogs,restoreStore,type RoundStore} from './rounds'

const ids=['a','b','c','d','e','f']
const make=(id='round-1')=>createRound(ids,'selection',false,()=>.23,'2026-10-17T01:00:00Z',id)
const hear=(round=make(),caseId='a',letter:'A'|'B'='A')=>markHeard(round,{roundId:round.id,caseId,letter,status:'complete'},`heard-${letter}`)
const store=(current=make()):RoundStore=>({schema:'harbeat.bass-neighbors-rounds.v1',current,history:[],playerLogs:[]})

describe('neighbor A/B rounds',()=>{
 it('uses only reference and stem, each orientation exactly three times',()=>{
  const mappings=Object.values(make().cases).map(c=>c.mapping)
  expect(mappings.filter(m=>m.A==='reference'&&m.B==='stem')).toHaveLength(3)
  expect(mappings.filter(m=>m.A==='stem'&&m.B==='reference')).toHaveLength(3)
 })
 it('accepts an early choice and freezes heard state at the first choice',()=>{
  const chosen=recordChoice(hear(),'a','A','first')
  expect(canVote(make(),'a')).toBe(true)
  expect(canVote(make(),'missing')).toBe(false)
  expect(chosen.cases.a.firstBlindChoice).toEqual({choice:'A',at:'first',heard:{A:'heard-A'}})
  const edited=recordChoice(hear(chosen,'a','B'),'a','B','edit')
  expect(edited.cases.a.firstBlindChoice).toEqual({choice:'A',at:'first',heard:{A:'heard-A'}})
  expect(edited.cases.a.votes).toEqual([{choice:'A',at:'first',afterReveal:false,heard:{A:'heard-A'}},{choice:'B',at:'edit',afterReveal:false,heard:{A:'heard-A',B:'heard-B'}}])
  expect(edited.cases.a.choice).toBe('B')
 })
 it('does not accept stale rounds, partial playback or unknown letters as complete',()=>{
  const r=make()
  for(const event of [{roundId:'old',caseId:'a',letter:'A',status:'complete'},{roundId:r.id,caseId:'a',letter:'A',status:'idle'},{roundId:r.id,caseId:'a',letter:'C',status:'complete'},{roundId:r.id,caseId:'missing',letter:'A',status:'complete'}])expect(markHeard(r,event)).toBe(r)
  expect(hear(r).cases.a.heard).toEqual({A:'heard-A'})
 })
 it('blocks all formal reveals until six choices, without requiring full plays',()=>{
  let r=make()
  for(const id of ids.slice(0,5))r=recordChoice(r,id,'tie','first')
  expect(revealCase(r,'a','too-early')).toBe(r)
  r=recordChoice(r,'f','none','last')
  expect(revealCase(r,'a','allowed').cases.a.revealedAt).toBe('allowed')
 })
 it('allows practice reveal after its choice and preserves the first reveal and vote',()=>{
  const practice=setPractice(make(),true)
  expect(revealCase(practice,'a')).toBe(practice)
  const chosen=recordChoice(practice,'a','A','first')
  const revealed=revealCase(chosen,'a','reveal')
  const edited=recordChoice(revealCase(revealed,'a','later'),'a','none','edit')
  expect(edited.cases.a.revealedAt).toBe('reveal')
  expect(edited.cases.a.firstBlindChoice?.choice).toBe('A')
  expect(edited.cases.a.votes[1].afterReveal).toBe(true)
 })
 it('locks practice after voting as well as playback, to prevent reclassifying an entered round',()=>{
  const voted=recordChoice(make(),'a','A','first')
  expect(setPractice(voted,true)).toBe(voted)
  const started={...make(),startedAt:'start'}
  expect(setPractice(started,true)).toBe(started)
 })
 it('archives feedback and logs while a new round starts empty',()=>{
  const old=updateFeedback(recordChoice(hear(),'a','B','first'),'a',['kick-weaker'],'鼓轻了')
  const logged=withPlayerLogs(withPlayerLogs(store(old),'one',[{event:'play'}]),'two',[{event:'play'}])
  const next=archiveRound(withPlayerLogs(logged,'two',[{event:'play'},{event:'complete'}]),make('next'))
  expect(next.history).toEqual([old])
  expect(next.current.cases.a.heard).toEqual({})
  expect(next.current.cases.a.firstBlindChoice).toBeUndefined()
  expect(next.playerLogs).toEqual([{sessionId:'one',logs:[{event:'play'}]},{sessionId:'two',logs:[{event:'play'},{event:'complete'}]}])
 })
 it('restores assignments and heard snapshots without changing old records',()=>{
  const saved=store(recordChoice(hear(),'a','A','first'))
  expect(restoreStore(JSON.stringify(saved),make('fresh'))).toEqual(saved)
  expect(restoreStore(null,make())).toEqual(store())
 })
 it('rejects EQ, duplicate modes or unbalanced assignments before a save',()=>{
  for(const mapping of [{A:'reference',B:'eq'},{A:'reference',B:'reference'}]){
   const saved=store();Object.assign(saved.current.cases.a,{mapping})
   expect(()=>restoreStore(JSON.stringify(saved),make())).toThrow('本机记录')
  }
  const saved=store();for(const c of Object.values(saved.current.cases))c.mapping={A:'reference',B:'stem'}
  expect(()=>restoreStore(JSON.stringify(saved),make())).toThrow('本机记录')
 })
 it('rejects invalid first choice snapshots instead of silently overwriting',()=>{
  const saved=store(recordChoice(make(),'a','A','first'))
  Object.assign(saved.current.cases.a.firstBlindChoice!,{heard:{C:'invalid'}})
  expect(()=>restoreStore(JSON.stringify(saved),make())).toThrow('本机记录')
 })
 it('archives provenance on a pack change and rejects case mismatches on the same pack',()=>{
  const old={...make(),sourceSnapshot:{old:'provenance'}}
  const fresh={...make('next'),selectionSha256:'new'}
  const restored=restoreStore(JSON.stringify(store(old)),fresh)
  expect(restored.history).toEqual([old]);expect(restored.current).toEqual(fresh)
  const changed=createRound(['g','h','i','j','k','l'],'selection',false,()=>.2,'time','changed')
  expect(()=>restoreStore(JSON.stringify(store(old)),changed)).toThrow('本机记录')
 })
})
