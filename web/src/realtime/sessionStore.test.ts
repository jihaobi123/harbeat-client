import {it,expect,vi} from 'vitest'
import {SessionWriter,validateSession} from './sessionStore'
it('rejects malformed imports and accepts historical session snapshots',()=>{
 expect(()=>validateSession({sessionId:'x',logs:[]})).toThrow()
 expect(validateSession({schema:'harbeat.v3_live_session.v2',sessionId:'s',catalog:[{id:'historical'}],logs:[]}).catalog[0].title).toBe('historical')
})
it('serializes writes and keeps a final newer snapshot during an in-flight save',async()=>{
 let version=1,release:()=>void=()=>{};const writes:number[]=[]
 const writer=new SessionWriter(()=>({version}),async x=>{writes.push(x.version);if(x.version===1)await new Promise<void>(r=>release=r)},()=>{})
 const first=writer.flush();version=2;const second=writer.flush();release();await Promise.all([first,second]);expect(writes).toEqual([1,2])
})
it('reports storage failure without pretending the session was saved',async()=>{const status=vi.fn();const writer=new SessionWriter(()=>({}),async()=>{throw new Error('quota')},status);await writer.flush();expect(status).toHaveBeenCalledWith('保存失败：quota')})
