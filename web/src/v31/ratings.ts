export const RATINGS_KEY='harbeat-v31-ratings'
export const BACKUP_KEY='harbeat-v31-ratings-backup-20260924'
type Store=Pick<Storage,'getItem'|'setItem'>
export function readRatings(store:Store):Record<string,any>{
 const raw=store.getItem(RATINGS_KEY)
 if(raw!==null&&store.getItem(BACKUP_KEY)===null){try{store.setItem(BACKUP_KEY,raw)}catch{/* A full storage must not hide existing feedback. */}}
 const value=JSON.parse(raw||'{}')
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error('试听反馈格式异常，已保留原始记录，请先导出备份。')
 return value
}
export function writeRating(store:Store,fallback:Record<string,any>,id:string,value:any,dirty:Record<string,any>={}){
 const latest=readRatings(store),next={...fallback,...latest,...dirty,[id]:value}
 store.setItem(RATINGS_KEY,JSON.stringify(next));return next
}
