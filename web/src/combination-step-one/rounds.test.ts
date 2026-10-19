import {expect,it} from 'vitest'
import {createRound,recordChoice,markHeard,revealCase,restoreStore,letters} from './rounds'
it('maps three anonymous letters bijectively to original, selected single and one added technique',()=>{
 for(const r of [0,.24,.6,.99]){const c=createRound(['pair'],'source',false,()=>r).cases.pair;expect(letters).toEqual(['A','B','C']);expect(new Set(Object.values(c.mapping))).toEqual(new Set(['original','single','combined']));expect(new Set(c.recommendedOrder).size).toBe(3)}
})
it('permits early votes, retains initial choice on change and accepts C completion',()=>{
 let r=createRound(['pair'],'source');r=recordChoice(r,'pair','C','first');r=markHeard(r,{roundId:r.id,caseId:'pair',letter:'C',status:'complete'},'end');r=recordChoice(r,'pair','A','second');expect(r.cases.pair.firstBlindChoice).toEqual({choice:'C',at:'first',heard:{}});expect(r.cases.pair.choice).toBe('A');expect(r.cases.pair.heard.C).toBe('end');expect(r.cases.pair.votes).toHaveLength(2);expect(revealCase(r,'pair').cases.pair.revealedAt).toBeTruthy()
})
it('rejects corrupt tri-arm records without overwriting and archives changed pack identity',()=>{
 const r=createRound(['pair'],'source');const store:any={schema:'harbeat.combination-step-one-rounds.v1',current:r,history:[],playerLogs:[]};const changed=createRound(['pair'],'new-source');expect(restoreStore(JSON.stringify(store),changed).history).toHaveLength(1);store.current.cases.pair.mapping.C=store.current.cases.pair.mapping.A;expect(()=>restoreStore(JSON.stringify(store),r)).toThrow()
})
