import { afterEach, expect, it, vi } from 'vitest'
import { loadWorkspace } from './api'

afterEach(()=>vi.unstubAllGlobals())
it('publishes the library while job history is still pending',async()=>{
 let release!:(r:Response)=>void
 const jobs=new Promise<Response>(resolve=>{release=resolve})
 vi.stubGlobal('fetch',vi.fn((url:string)=>url.endsWith('/reports')?Promise.resolve(new Response(JSON.stringify([{id:'song'}]))):jobs))
 const onReports=vi.fn(),onJobs=vi.fn()
 const pending=loadWorkspace(onReports,onJobs)
 await vi.waitFor(()=>expect(onReports).toHaveBeenCalledWith([{id:'song'}]))
 expect(onJobs).not.toHaveBeenCalled()
 release(new Response('[]'));await pending
 expect(onJobs).toHaveBeenCalledWith([])
})
