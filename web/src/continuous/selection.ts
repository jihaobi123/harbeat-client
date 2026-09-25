import type {Track} from '../realtime/planner'
export type SelectionState={id:string|null;status:'idle'|'loading'|'queued'|'ready'|'failed';error:string}
export class NextSelection{
 state:SelectionState={id:null,status:'idle',error:''}
 private revision=0
 constructor(private load:(id:string)=>Promise<Track>,private port:{install:(track:Track)=>void;prepare:(id:string)=>Promise<void>;prepareCandidates?:(ids:string[])=>Promise<string>},private changed:(state:SelectionState)=>void){}
 private set(state:SelectionState){this.state=state;this.changed(state)}
 async select(id:string,options:{defer?:boolean}={}){
  const revision=++this.revision;this.set({id,status:'loading',error:''})
  try{
   const track=await this.load(id);if(revision!==this.revision)return
   this.port.install(track);if(options.defer){this.set({id,status:'queued',error:''});return}
   await this.port.prepare(id);if(revision!==this.revision)return
   this.set({id,status:'ready',error:''})
  }catch(error){if(revision===this.revision)this.set({id,status:'failed',error:(error as Error).message})}
 }
 async selectCandidates(ids:string[]){
  if(!ids.length){this.clear();return}
  const revision=++this.revision;this.set({id:ids[0],status:'loading',error:''})
  try{
   const loaded=await Promise.allSettled(ids.map(id=>this.load(id)));if(revision!==this.revision)return
   const tracks=loaded.flatMap(r=>r.status==='fulfilled'?[r.value]:[])
   if(!tracks.length)throw Error('候选歌曲资料暂时无法读取，请稍后重试。')
   for(const track of tracks)this.port.install(track)
   if(!this.port.prepareCandidates)throw Error('自动选曲尚未配置')
   const id=await this.port.prepareCandidates(tracks.map(t=>t.id));if(revision!==this.revision)return
   this.set({id,status:'ready',error:''})
  }catch(error){if(revision===this.revision)this.set({id:ids[0],status:'failed',error:(error as Error).message})}
 }
 cancelPending(){this.revision++;if(this.state.status==='loading')this.set({...this.state,status:'idle',error:''})}
 clear(){this.revision++;this.set({id:null,status:'idle',error:''})}
}
