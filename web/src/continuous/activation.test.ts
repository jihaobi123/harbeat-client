import {describe,expect,it,vi} from 'vitest'
import {initializeFromGesture} from './activation'

describe('first user gesture',()=>{
 it('unlocks audio synchronously before waiting for the worklet or metadata',async()=>{
  const order:string[]=[]
  let finish!:()=>void
  const worklet=new Promise<void>(resolve=>{finish=resolve})
  const player={ctx:{resume:vi.fn(()=>{order.push('resume');return Promise.resolve()})},
   initialize:vi.fn(()=>{order.push('initialize');return worklet})}
  let complete=false
  const task=initializeFromGesture(player).then(()=>{complete=true})
  expect(order).toEqual(['resume','initialize'])
  await Promise.resolve();expect(complete).toBe(false)
  finish();await task;expect(complete).toBe(true)
 })
 it('propagates activation rejection so the player can be disposed and retried',async()=>{
  const player={ctx:{resume:()=>Promise.reject(new Error('activation denied'))},initialize:()=>Promise.resolve()}
  await expect(initializeFromGesture(player)).rejects.toThrow('activation denied')
 })
})
