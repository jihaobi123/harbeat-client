import {describe,it,expect} from 'vitest'
import {RoundPersistence,type RawBackend} from './storage'
import {createRound,restoreStore} from './rounds'

describe('durable round storage',()=>{
 it('serializes writes so a slow older snapshot cannot replace newer choices',async()=>{
  let release!:()=>void,raw:string|null=null
  const firstWrite=new Promise<void>(resolve=>{release=resolve})
  const started:string[]=[]
  const backend:RawBackend={read:async()=>raw,write:async value=>{started.push(value);if(value==='older')await firstWrite;raw=value}}
  const persistence=new RoundPersistence(backend,()=>null)
  const older=persistence.save('older'),newer=persistence.save('newer')
  await Promise.resolve()
  expect(started).toEqual(['older'])
  release();await Promise.all([older,newer])
  expect((await persistence.load()).raw).toBe('newer')
 })
 it('loads untouched legacy history, then restores the full store from the new backend',async()=>{
  const current=createRound(['a','b','c','d','e','f'],'selection'),history=[{...current,id:'archived',sourceSnapshot:{large:'original source'}}]
  const legacy=JSON.stringify({schema:'harbeat.bass-generalization-rounds.v1',current,history,playerLogs:[{sessionId:'old-session',logs:[{event:'complete'}]}]})
  let raw:string|null=null
  const backend:RawBackend={read:async()=>raw,write:async value=>{raw=value}}
  const persistence=new RoundPersistence(backend,()=>legacy)
  const initial=await persistence.load()
  expect(initial.source).toBe('legacy')
  expect(raw).toBeNull()
  const restored=restoreStore(initial.raw,current)
  await persistence.save(JSON.stringify(restored))
  const reload=await new RoundPersistence(backend,()=>legacy).load()
  expect(reload.source).toBe('indexeddb')
  expect(JSON.parse(reload.raw!).history).toEqual(history)
  expect((await persistence.recover()).legacyLocalStorage.raw).toBe(legacy)
 })
 it('reports a failed write and permits later snapshots to save',async()=>{
  let fail=true,raw:string|null=null
  const persistence=new RoundPersistence({read:async()=>raw,write:async value=>{if(fail){fail=false;throw Error('quota')}raw=value}},()=>null)
  await expect(persistence.save('first')).rejects.toThrow('quota')
  await persistence.save('second')
  expect((await persistence.load()).raw).toBe('second')
 })
 it('protects unreadable backend data and exports actual backend plus legacy recovery',async()=>{
  let writes=0
  const persistence=new RoundPersistence({read:async()=>{throw Error('backend unavailable')},write:async()=>{writes++}},()=> 'legacy records')
  const result=await persistence.load()
  expect(result.raw).toBe('legacy records')
  expect(result.warning).toContain('backend unavailable')
  await expect(persistence.save('fresh')).rejects.toThrow()
  expect(writes).toBe(0)
  const recovery=await persistence.recover()
  expect(recovery.indexedDB.error).toContain('backend unavailable')
  expect(recovery.legacyLocalStorage.raw).toBe('legacy records')
 })
})
