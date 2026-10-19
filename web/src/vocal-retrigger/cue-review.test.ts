import {expect,it} from 'vitest'
import {createRound,canVote,recordChoice,setCueReview,markCuePlayed,restoreStore} from './rounds'
it('requires explicit complete cue judgment before any blind preference, then allows an early vote',()=>{
 let r=createRound(['one'],'hash',false,()=>0,'created','round');expect(canVote(r,'one')).toBe(false);expect(recordChoice(r,'one','A')).toBe(r);r=markCuePlayed(r,'one','context','listen');expect(setCueReview(r,'one','complete','premature')).toBe(r);r=markCuePlayed(r,'one','sample','sample');r=setCueReview(r,'one','complete','review');expect(canVote(r,'one')).toBe(true);r=recordChoice(r,'one','A','vote');expect(r.cases.one.firstBlindChoice).toMatchObject({choice:'A',heard:{},cueReview:{status:'complete',sourceSelectionSha256:'hash'}})
})
it('preserves review history and review-at-vote when complete is later revoked',()=>{
 let r=createRound(['one'],'hash',false,()=>0,'created','round');r=markCuePlayed(markCuePlayed(r,'one','context'),'one','sample');r=setCueReview(r,'one','complete','yes');r=recordChoice(r,'one','A','vote');r=setCueReview(r,'one','cut','no');expect(canVote(r,'one')).toBe(false);expect(r.cases.one.firstBlindChoice).toMatchObject({cueReview:{status:'complete'}});expect((r.cases.one as any).cueReview.status).toBe('cut');expect((r.cases.one as any).cueReview.revisions).toHaveLength(2)
 const raw=JSON.stringify({schema:'harbeat.vocal-retrigger-rounds.v1',current:r,history:[],playerLogs:[]});expect(restoreStore(raw,r).current).toEqual(r)
})

it('rejects a saved complete review without both source exposures',()=>{
 const r=createRound(['one'],'hash',false,()=>0,'created','round');r.cases.one.cueReview.status='complete';
 expect(()=>restoreStore(JSON.stringify({schema:'harbeat.vocal-retrigger-rounds.v1',current:r,history:[],playerLogs:[]}),r)).toThrow()
})
