import {expect,it} from 'vitest'
import {createRound,recordChoice,revealCase,restoreStore} from '../combination-step-one/rounds'
it('requires all three fixed-pair initial votes before formal reveal, while permitting early C votes',()=>{
 let r=createRound(['neighbor-1','neighbor-2','neighbor-3'],'neighbors-source');r=recordChoice(r,'neighbor-1','C');expect(r.cases['neighbor-1'].heard).toEqual({});expect(revealCase(r,'neighbor-1').cases['neighbor-1'].revealedAt).toBeUndefined();r=recordChoice(r,'neighbor-2','tie');expect(revealCase(r,'neighbor-1').cases['neighbor-1'].revealedAt).toBeUndefined();r=recordChoice(r,'neighbor-3','B');expect(revealCase(r,'neighbor-1').cases['neighbor-1'].revealedAt).toBeTruthy();expect(r.cases['neighbor-2'].recommendedOrder).toEqual(['C','B','A']);expect(r.cases['neighbor-3'].recommendedOrder).toEqual(['A','B','C'])
})
it('keeps three independent case choices through durable reload without overwriting an earlier pack',()=>{
 let r=createRound(['n1','n2','n3'],'replication');r=recordChoice(r,'n2','B');const store:any={schema:'harbeat.combination-step-one-rounds.v1',current:r,history:[],playerLogs:[]};const loaded=restoreStore(JSON.stringify(store),createRound(['n1','n2','n3'],'replication'));expect(loaded.current.cases.n1.choice).toBeUndefined();expect(loaded.current.cases.n2.choice).toBe('B');const changed=restoreStore(JSON.stringify(store),createRound(['n1','n2','n3'],'changed'));expect(changed.history[0].cases.n2.choice).toBe('B')
})
