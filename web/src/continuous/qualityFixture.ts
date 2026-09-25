import type {Track} from '../realtime/planner'
export function qualityTrack(id:string):Track {
  const t:Track = {id,title:id,bpm:120,style:'Trap',styleScore:1,duration:80,reportId:'report'+id,
    native:{url:id,sha256:'native-'+id,duration:80,bytes:1},
    provenance:{masterSha256:'m'+id,reportSha256:'r'+id,vocalSha256:'v'+id,runId:'run'+id},
    bars:Array.from({length:40},(_,i)=>i*2),sections:[{start:0,end:80,label:'verse'}],
    vocals:id==='a'?[[2.3,5.7]]:[[.3,3.7]],energy:[{start:0,end:80,value:.4}],
    windows:[{id:'w',start:0,end:8,bars:4,role:'intro',energy:.4,
      variants:{a:{url:'clip',sha256:'clip-sha',duration:8,bytes:1,rate:1}}}],
    alignment:{schema:'x',status:'candidate',source:{reportId:'report'+id,masterSha256:'m'+id,reportSha256:'r'+id,vocalSha256:'v'+id},
      bars:[],phrases:[],exits:[],conflicts:[],
      bandFrames:[{start:0,end:80,rmsDbfs:-15,low:-20,mid:-22,high:-30}],limitations:[]}}
  t.preprocessing={schema:'harbeat.preprocessing-evidence.v1',reportId:t.reportId!,reportSha256:'r'+id,masterSha256:'m'+id,reportSnapshotUrl:'report.json',bindingChecks:{reportHash:true,masterHash:true},sections:{items:[]},beatGrid:{bars_ms:[],beats_ms:[]},tempo:{},vocalActivity:{status:'ready',time_origin:'master_audio_start',unit:'ms',source:{track_id:id,analysis_run_id:'run'+id,vocal_sha256:'v'+id},intervals:t.vocals!.map(([s,e])=>({start_ms:s*1000,end_ms:e*1000}))},vocalRms:{points:[]},energy:{},genre:{},extensions:[]}
  t.alignment!.bars=Array.from({length:40},(_,i)=>({index:i,start:i*2,end:i*2+2,lastBeat:i*2+1.5,beats:[0,.5,1,1.5].map(x=>i*2+x),valid:true}))
  return t
}
