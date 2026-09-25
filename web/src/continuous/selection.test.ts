import {it,expect,vi} from 'vitest'
import {NextSelection} from './selection'
import type {Track} from '../realtime/planner'
const track=(id:string)=>({id,title:id} as Track)
it('installs only the latest selection when older metadata finishes late',async()=>{
 let finishOld!:(t:Track)=>void
 const prepare=vi.fn(async()=>{}),install=vi.fn(),events:any[]=[]
 const selection=new NextSelection(id=>id==='old'?new Promise(r=>{finishOld=r}):Promise.resolve(track(id)),{install,prepare},s=>events.push(s))
 const old=selection.select('old');await selection.select('new');finishOld(track('old'));await old
 expect(selection.state).toMatchObject({id:'new',status:'ready'})
 expect(install.mock.calls.map(c=>c[0].id)).toEqual(['new']);expect(prepare).toHaveBeenCalledWith('new')
})
it('does not restore a cleared next-song selection when preparation completes',async()=>{
 let finish!:()=>void
 const selection=new NextSelection(async id=>track(id),{install:()=>{},prepare:()=>new Promise(r=>{finish=r})},()=>{})
 const pending=selection.select('a');await Promise.resolve();selection.clear();finish();await pending
 expect(selection.state).toEqual({id:null,status:'idle',error:''})
})
it('shows preparation errors and a later selection can recover',async()=>{
 const selection=new NextSelection(async id=>track(id),{install:()=>{},prepare:async id=>{if(id==='bad')throw Error('素材读取失败')}},()=>{})
 await selection.select('bad');expect(selection.state).toMatchObject({status:'failed',error:'素材读取失败'})
 await selection.select('good');expect(selection.state).toMatchObject({id:'good',status:'ready',error:''})
})
it('keeps a future selection queued during a committed handoff and prepares it for the new source later',async()=>{
 const prepare=vi.fn(async()=>{}),install=vi.fn()
 const selection=new NextSelection(async id=>track(id),{install,prepare},()=>{})
 await selection.select('c',{defer:true})
 expect(selection.state).toMatchObject({id:'c',status:'queued'})
 expect(install).toHaveBeenCalledTimes(1);expect(prepare).not.toHaveBeenCalled()
 await selection.select('c')
 expect(selection.state).toMatchObject({id:'c',status:'ready'});expect(prepare).toHaveBeenCalledTimes(1);expect(prepare).toHaveBeenCalledWith('c')
})

it('loads shortlist metadata, retains a healthy candidate when another fails, and displays the chosen winner',async()=>{
 const port={install:vi.fn(),prepare:vi.fn(),prepareCandidates:vi.fn(async()=> 'c')}
 const selection=new NextSelection(async id=>{if(id==='b')throw Error('metadata unavailable');return {id} as any},port,()=>{})
 await selection.selectCandidates(['b','c','d'])
 expect(port.prepareCandidates).toHaveBeenCalledWith(['c','d'])
 expect(selection.state).toEqual({id:'c',status:'ready',error:''})
})
it('manual replacement prevents a stale shortlist from preparing or selecting a different song',async()=>{
 let finish!:(track:any)=>void
 const port={install:vi.fn(),prepare:vi.fn(async()=>{}),prepareCandidates:vi.fn(async()=> 'b')}
 const selection=new NextSelection(id=>id==='b'?new Promise(r=>{finish=r}):Promise.resolve({id} as any),port,()=>{})
 const pending=selection.selectCandidates(['b']);await selection.select('c');finish({id:'b'});await pending
 expect(selection.state.id).toBe('c');expect(port.prepareCandidates).not.toHaveBeenCalled()
})

it('invalidating metadata work retains selection but cannot start automatic preparation after toggling off',async()=>{
 let finish!:(track:any)=>void
 const port={install:vi.fn(),prepare:vi.fn(async()=>{}),prepareCandidates:vi.fn(async()=> 'b')}
 const selection=new NextSelection(()=>new Promise(r=>{finish=r}),port,()=>{})
 const task=selection.selectCandidates(['b']);selection.cancelPending();finish({id:'b'});await task
 expect(port.prepareCandidates).not.toHaveBeenCalled();expect(selection.state.id).toBe('b');expect(selection.state.status).toBe('idle')
})
