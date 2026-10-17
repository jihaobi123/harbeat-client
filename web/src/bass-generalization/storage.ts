export type RawBackend={read:()=>Promise<string|null>;write:(raw:string)=>Promise<void>}
type RawRecovery={raw:string|null;error?:string}
const message=(error:unknown)=>error instanceof Error?error.message:String(error)

/** Serialize immutable snapshots; a rejected write never blocks a later retry. */
export class RoundPersistence{
 private pending:Promise<void>=Promise.resolve()
 private readFailure?:Error
 constructor(private backend:RawBackend,private legacyRead:()=>string|null){}
 save(raw:string):Promise<void>{
  const writing=this.pending.then(()=>{if(this.readFailure)throw this.readFailure;return this.backend.write(raw)})
  this.pending=writing.catch(()=>{})
  return writing
 }
 async load():Promise<{raw:string|null;source:'indexeddb'|'legacy'|'empty';warning?:string}>{
  await this.pending
  let warning:string|undefined
  try{const raw=await this.backend.read();this.readFailure=undefined;if(raw!==null)return {raw,source:'indexeddb'}}
  catch(error){this.readFailure=Error(message(error));warning=message(error)}
  try{const raw=this.legacyRead();return {raw,source:raw===null?'empty':'legacy',warning}}
  catch(error){return {raw:null,source:'empty',warning:[warning,message(error)].filter(Boolean).join('; ')}}
 }
 async recover():Promise<{indexedDB:RawRecovery;legacyLocalStorage:RawRecovery}>{
  await this.pending
  let indexedDB:RawRecovery,legacyLocalStorage:RawRecovery
  try{indexedDB={raw:await this.backend.read()}}catch(error){indexedDB={raw:null,error:message(error)}}
  try{legacyLocalStorage={raw:this.legacyRead()}}catch(error){legacyLocalStorage={raw:null,error:message(error)}}
  return {indexedDB,legacyLocalStorage}
 }
}

export const databaseName='harbeat.bass-generalization.v1'
export const objectStoreName='rounds'
export const recordKey='all-rounds'

/** Keep the full history and source evidence in IndexedDB, outside localStorage's small quota. */
export function indexedDBBackend(name=databaseName):RawBackend{
 let opening:Promise<IDBDatabase>|undefined
 function database():Promise<IDBDatabase>{
  if(opening)return opening
  opening=new Promise<IDBDatabase>((resolve,reject)=>{
   if(!globalThis.indexedDB){reject(Error('当前浏览器无法使用 IndexedDB'));return}
   const request=indexedDB.open(name,1)
   let blocked=false
   request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains(objectStoreName))request.result.createObjectStore(objectStoreName)}
   request.onsuccess=()=>{if(blocked){request.result.close();return}request.result.onversionchange=()=>request.result.close();resolve(request.result)}
   request.onerror=()=>reject(request.error??Error('本机记录数据库打开失败'))
   request.onblocked=()=>{blocked=true;reject(Error('本机记录数据库被其他页面占用，请关闭旧页面后重试'))}
  }).catch(error=>{opening=undefined;throw error})
  return opening
 }
 return {
  async read(){
   const db=await database()
   return new Promise<string|null>((resolve,reject)=>{
    const tx=db.transaction(objectStoreName,'readonly'),request=tx.objectStore(objectStoreName).get(recordKey)
    let raw:string|null=null
    request.onsuccess=()=>{raw=request.result??null}
    tx.oncomplete=()=>resolve(raw)
    tx.onerror=()=>reject(tx.error??request.error??Error('本机记录读取失败'))
    tx.onabort=()=>reject(tx.error??Error('本机记录读取中断'))
   })
  },
  async write(raw){
   const db=await database()
   return new Promise<void>((resolve,reject)=>{
    const tx=db.transaction(objectStoreName,'readwrite'),request=tx.objectStore(objectStoreName).put(raw,recordKey)
    tx.oncomplete=()=>resolve()
    tx.onerror=()=>reject(tx.error??request.error??Error('本机记录保存失败'))
    tx.onabort=()=>reject(tx.error??Error('本机记录保存中断'))
   })
  }
 }
}
