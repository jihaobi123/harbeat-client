export type SessionSnapshot={schema:string;sessionId:string;catalog:any[];logs:any[];savedAt?:string;[key:string]:any}
export type SessionIndex={sessionId:string;savedAt:string;requests:number;events:number;tracks:string[]}
export function validateSession(value:any):SessionSnapshot{
 if(!value||!['harbeat.v3_live_session.v1','harbeat.v3_live_session.v2'].includes(value.schema)||typeof value.sessionId!=='string'||!value.sessionId||value.sessionId.length>200||!Array.isArray(value.catalog)||!Array.isArray(value.logs)||value.logs.length>100000)throw new Error('不是支持的 V3 会话日志，请从播放页导出完整 JSON')
 if(value.logs.some((x:any)=>!x||typeof x.kind!=='string')||value.catalog.some((x:any)=>!x||typeof x.id!=='string'||(x.title!==undefined&&typeof x.title!=='string')))throw new Error('日志事件或素材来源格式不完整')
 return {...value,catalog:value.catalog.map((x:any)=>({...x,title:x.title||x.id}))}
}
function openDB():Promise<IDBDatabase>{return new Promise((resolve,reject)=>{
 if(typeof indexedDB==='undefined'){reject(new Error('浏览器不支持本地数据库'));return}
 const r=indexedDB.open('harbeat-mix-audit',1)
 r.onupgradeneeded=()=>{const db=r.result;db.createObjectStore('sessions',{keyPath:'sessionId'});db.createObjectStore('index',{keyPath:'sessionId'}).createIndex('savedAt','savedAt')}
 r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);r.onblocked=()=>reject(new Error('本地数据库被其他页面占用'))
})}
export async function saveSession(value:SessionSnapshot){
 const snapshot=validateSession(value),db=await openDB(),savedAt=new Date().toISOString()
 const summary:SessionIndex={sessionId:snapshot.sessionId,savedAt,requests:snapshot.logs.filter(x=>x.kind==='request_received').length,events:snapshot.logs.length,tracks:snapshot.catalog.map(x=>x.title)}
 await new Promise<void>((resolve,reject)=>{const tx=db.transaction(['sessions','index'],'readwrite');tx.objectStore('sessions').put({...snapshot,savedAt});tx.objectStore('index').put(summary);tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error('写入中断'))}).finally(()=>db.close())
 if(typeof window!=='undefined'){window.dispatchEvent(new Event('harbeat-session-saved'));if(window.parent!==window)window.parent.postMessage({kind:'harbeat-session-saved'},window.location.origin)}
}
export async function listSessions():Promise<SessionIndex[]>{const db=await openDB();return new Promise<SessionIndex[]>((resolve,reject)=>{const r=db.transaction('index').objectStore('index').getAll();r.onsuccess=()=>resolve(r.result.sort((a:SessionIndex,b:SessionIndex)=>b.savedAt.localeCompare(a.savedAt)));r.onerror=()=>reject(r.error)}).finally(()=>db.close())}
export async function readSession(id:string):Promise<SessionSnapshot>{const db=await openDB();return new Promise<SessionSnapshot>((resolve,reject)=>{const r=db.transaction('sessions').objectStore('sessions').get(id);r.onsuccess=()=>{try{resolve(validateSession(r.result))}catch(e){reject(e)}};r.onerror=()=>reject(r.error)}).finally(()=>db.close())}
// One writer per immutable session ID; concurrent updates coalesce and never overtake older writes.
export class SessionWriter{
 private timer:ReturnType<typeof setTimeout>|null=null;private running:Promise<void>|null=null;private dirty=false
 constructor(private snapshot:()=>any,private save:(x:any)=>Promise<void>,private status:(text:string)=>void){}
 queue(){this.dirty=true;if(this.timer===null)this.timer=setTimeout(()=>{this.timer=null;void this.flush()},500)}
 flush():Promise<void>{if(this.timer!==null){clearTimeout(this.timer);this.timer=null}this.dirty=true;if(this.running)return this.running
  this.running=(async()=>{while(this.dirty){this.dirty=false;try{await this.save(this.snapshot());this.status('已保存到本浏览器')}catch(e){this.status('保存失败：'+(e as Error).message)}}})().finally(()=>{this.running=null})
  return this.running
 }
}
