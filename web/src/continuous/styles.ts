import {suggestNext,type LibraryEntry} from './catalog'
// Human library labels are the user's style taxonomy. A model's "Pop" label
// must not erase distinctions such as house, jazz hiphop, KPOP, and EDM.
export function styleChoices(entries:LibraryEntry[]){
 const counts=new Map<string,number>()
 for(const e of entries)if(e.playStatus==='ready'&&e.mixStatus==='ready')for(const label of new Set(e.styleLabels))counts.set(label,(counts.get(label)||0)+1)
 return [...counts].map(([key,count])=>({key,count})).sort((a,b)=>a.key.localeCompare(b.key))
}
export function pickStyle(entries:LibraryEntry[],current:LibraryEntry,style:string,recent:string[]){
 return suggestNext(entries.filter(e=>e.styleLabels.includes(style)),current,recent)
}
