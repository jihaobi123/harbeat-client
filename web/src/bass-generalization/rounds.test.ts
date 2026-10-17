import {describe,it,expect} from 'vitest'
import {createRound,markHeard,recordChoice,revealCase,setPractice,archiveRound,updateFeedback,canVote,withPlayerLogs,restoreStore} from './rounds'

const ids=['anchor','edm','kpop','amapiano','funk','jazz']
const make=(id='round-1')=>createRound(ids,'selection',false,()=>.23,'2026-10-17T01:00:00Z',id)
const hearAll=(round=make(),caseId='anchor')=>(['A','B','C'] as const).reduce((r,letter)=>markHeard(r,{roundId:r.id,caseId,letter,status:'complete'},'heard-time'),round)

describe('blind coverage rounds',()=>{
 it('uses every permutation once, with two occurrences per letter for each method',()=>{
  const round=make(),mappings=Object.values(round.cases).map(c=>c.mapping)
  expect(new Set(mappings.map(m=>JSON.stringify(m))).size).toBe(6)
  for(const letter of ['A','B','C'] as const)for(const mode of ['reference','stem','eq'])expect(mappings.filter(m=>m[letter]===mode)).toHaveLength(2)
  expect(JSON.parse(JSON.stringify(round)).cases).toEqual(round.cases)
 })
 it('only a completed matching round and letter earns a heard mark',()=>{
  const round=make()
  expect(markHeard(round,{roundId:'old-round',caseId:'anchor',letter:'A',status:'complete'},'time')).toBe(round)
  expect(markHeard(round,{roundId:round.id,caseId:'anchor',letter:'A',status:'idle'},'time')).toBe(round)
  expect(markHeard(round,{roundId:round.id,caseId:'missing',letter:'A',status:'complete'},'time')).toBe(round)
  expect(markHeard(round,{roundId:round.id,caseId:'anchor',letter:'A',status:'complete'},'time').cases.anchor.heard).toEqual({A:'time'})
 })
 it('accepts a choice without full plays and preserves the original blind choice after edits',()=>{
  const round={...make(),practice:true}
  expect(canVote(round,'anchor')).toBe(true)
  expect(canVote(round,'missing')).toBe(false)
  const chosen=recordChoice(round,'anchor','A','first-time')
  expect(chosen.cases.anchor.heard).toEqual({})
  const revealed=revealCase(chosen,'anchor','reveal-time')
  const edited=recordChoice(revealed,'anchor','none','edit-time')
  expect(edited.cases.anchor.firstBlindChoice).toEqual({choice:'A',at:'first-time'})
  expect(edited.cases.anchor.choice).toBe('none')
  expect(edited.cases.anchor.votes).toEqual([{choice:'A',at:'first-time',afterReveal:false},{choice:'none',at:'edit-time',afterReveal:true}])
  expect(edited.cases.anchor.revealedAt).toBe('reveal-time')
 })
 it('cannot reveal before a choice and retains the first reveal time',()=>{
  expect(revealCase(make(),'anchor','time').cases.anchor.revealedAt).toBeUndefined()
  const chosen=recordChoice(hearAll({...make(),practice:true}),'anchor','tie','first')
  expect(revealCase(revealCase(chosen,'anchor','reveal'),'anchor','later').cases.anchor.revealedAt).toBe('reveal')
 })
 it('blocks every formal reveal until all six first blind choices are recorded',()=>{
  let round=make()
  for(const caseId of ids.slice(0,5))round=recordChoice(hearAll(round,caseId),caseId,'tie','first')
  expect(revealCase(round,'anchor','too-early')).toBe(round)
  round=recordChoice(hearAll(round,'jazz'),'jazz','A','last-first-choice')
  expect(revealCase(round,'anchor','allowed').cases.anchor.revealedAt).toBe('allowed')
 })
 it('archives the full prior round and creates fresh heard, choices and mappings',()=>{
  const old=updateFeedback(recordChoice(hearAll(),'anchor','B','first'),'anchor',['kick-weaker'],'听起来有点空')
  const store={schema:'harbeat.bass-generalization-rounds.v1' as const,current:old,history:[],playerLogs:[]}
  const next=archiveRound(store,createRound(ids,'selection',false,()=>.8,'later','round-2'))
  expect(next.history).toEqual([old])
  expect(next.current.cases.anchor.heard).toEqual({})
  expect(next.current.cases.anchor.firstBlindChoice).toBeUndefined()
  expect(next.current.cases.anchor.mapping).not.toEqual(old.cases.anchor.mapping)
  expect(next.history[0].cases.anchor.notes).toBe('听起来有点空')
 })
 it('locks practice classification once playback has started',()=>{
  const practice=setPractice(make(),true)
  expect(practice.practice).toBe(true)
  const started={...practice,startedAt:'start-time'}
  expect(setPractice(started,false)).toBe(started)
 })
 it('keeps log sessions across reloads while replacing only the current session snapshot',()=>{
  const store={schema:'harbeat.bass-generalization-rounds.v1' as const,current:make(),history:[],playerLogs:[]}
  const a=withPlayerLogs(store,'session-a',[{event:'play'}])
  const b=withPlayerLogs(a,'session-b',[{event:'play'}])
  const c=withPlayerLogs(b,'session-b',[{event:'play'},{event:'complete'}])
  expect(c.playerLogs).toEqual([{sessionId:'session-a',logs:[{event:'play'}]},{sessionId:'session-b',logs:[{event:'play'},{event:'complete'}]}])
 })
 it('restores the same assignment and rejects duplicate methods before overwriting local records',()=>{
  const current=make(),store={schema:'harbeat.bass-generalization-rounds.v1' as const,current,history:[],playerLogs:[]}
  expect(restoreStore(JSON.stringify(store),make('unused-new-round'))).toEqual(store)
  const corrupt={...store,current:{...current,cases:{...current.cases,anchor:{...current.cases.anchor,mapping:{A:'reference',B:'reference',C:'eq'}}}}}
  expect(()=>restoreStore(JSON.stringify(corrupt),make())).toThrow('本机记录')
 })
 it('archives prior provenance and logs when the source selection changes',()=>{
  const old={...make(),sourceSnapshot:{selection:'old-pack'}},store={schema:'harbeat.bass-generalization-rounds.v1' as const,current:old,history:[],playerLogs:[{sessionId:'older-session',logs:[{event:'complete'}]}]}
  const fresh={...make('new-round'),selectionSha256:'new-selection',sourceSnapshot:{selection:'new-pack'}}
  const restored=restoreStore(JSON.stringify(store),fresh)
  expect(restored.current).toEqual(fresh)
  expect(restored.history).toEqual([old])
  expect(restored.playerLogs).toEqual(store.playerLogs)
 })
})
