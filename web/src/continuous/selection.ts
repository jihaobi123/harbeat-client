import type {Track} from '../realtime/planner'
export type SelectionState={id:string|null;status:'idle'|'loading'|'queued'|'ready'|'failed';error:string}
export class NextSelection{
 state:SelectionState={id:null,status:'idle',error:''}
 private revision=0
 constructor(private load:(id:string)=>Promise<Track>,private port:{install:(track:Track)=>void;prepare:(id:string)=>Promise<void>},private changed:(state:SelectionState)=>void){}
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
 clear(){this.revision++;this.set({id:null,status:'idle',error:''})}
}
