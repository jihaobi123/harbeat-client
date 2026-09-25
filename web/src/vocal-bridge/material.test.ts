import {it,expect} from 'vitest'
import {createHash} from 'node:crypto'
import {assertSelectionBinding} from './material'
const digest=(v:unknown)=>createHash('sha256').update(JSON.stringify(v)).digest('hex')
it('rejects a stale render even when a case id is reused',()=>{
 const selected={id:'same',start:50,bEntry:3,rate:1,masterSha256:'old',vocalSha256:'old-v',reportSha256:'report'}
 const renderedHash=digest(selected)
 expect(()=>assertSelectionBinding(renderedHash,digest(selected))).not.toThrow()
 for(const change of [{start:51},{bEntry:4},{rate:.97},{masterSha256:'new'},{vocalSha256:'new-v'},{reportSha256:'new-report'}])expect(()=>assertSelectionBinding(renderedHash,digest({...selected,...change}))).toThrow()
 expect(()=>assertSelectionBinding(undefined,renderedHash)).toThrow()
})
