export type Mode='reference'|'stem'

export const letters=['A','B'] as const
export type Letter=typeof letters[number]
export type Choice=Letter|'tie'|'none'
export type Symptom='bass-clearer'|'kick-weaker'|'low-end-empty'|'abrupt'|'voice-muddy'|'louder'|'quieter'
export type CaseFeedback={
 mapping:Record<Letter,Mode>;heard:Partial<Record<Letter,string>>
 firstBlindChoice?:{choice:Choice;at:string;heard:Partial<Record<Letter,string>>};choice?:Choice
 votes:{choice:Choice;at:string;afterReveal:boolean;heard:Partial<Record<Letter,string>>}[];revealedAt?:string
 symptoms:Symptom[];notes:string
}
export type Round={id:string;createdAt:string;selectionSha256:string;practice:boolean;startedAt?:string;sourceSnapshot?:unknown;cases:Record<string,CaseFeedback>}
export type RoundStore={schema:'harbeat.bass-neighbors-rounds.v1';current:Round;history:Round[];playerLogs:{sessionId:string;logs:unknown[]}[]}
export const storageKey='harbeat.bass-neighbors.v1.rounds'
const now=()=>new Date().toISOString()
const permutations:Mode[][]=[['reference','stem'],['reference','stem'],['reference','stem'],['stem','reference'],['stem','reference'],['stem','reference']]

export function createRound(caseIds:string[],selectionSha256:string,practice=false,random=Math.random,createdAt=now(),id:string=crypto.randomUUID()):Round{
 if(caseIds.length!==6||new Set(caseIds).size!==6)throw Error('平衡盲听需要六个不同的固定样例')
 const shuffled=permutations.map(p=>[...p])
 for(let i=shuffled.length-1;i>0;i--){const j=Math.min(i,Math.max(0,Math.floor(random()*(i+1))));[shuffled[i],shuffled[j]]=[shuffled[j],shuffled[i]]}
 return {id,createdAt,selectionSha256,practice,cases:Object.fromEntries(caseIds.map((caseId,i)=>[caseId,{mapping:{A:shuffled[i][0],B:shuffled[i][1]},heard:{},votes:[],symptoms:[],notes:''}]))}
}
export function markHeard(round:Round,event:{roundId?:string;caseId:string;letter?:string;status:string},at=now()):Round{
 const c=round.cases[event.caseId]
 if(event.status!=='complete'||event.roundId!==round.id||!c||!letters.includes(event.letter as Letter))return round
 const letter=event.letter as Letter
 if(c.heard[letter])return round
 return {...round,cases:{...round.cases,[event.caseId]:{...c,heard:{...c.heard,[letter]:at}}}}
}
export function canVote(round:Round,caseId:string){return !!round.cases[caseId]}
export function recordChoice(round:Round,caseId:string,choice:Choice,at=now()):Round{
 const c=round.cases[caseId]
 if(!c||!canVote(round,caseId))return round
 return {...round,cases:{...round.cases,[caseId]:{...c,choice,firstBlindChoice:c.firstBlindChoice??{choice,at,heard:{...c.heard}},votes:[...c.votes,{choice,at,afterReveal:!!c.revealedAt,heard:{...c.heard}}]}}}
}
export function revealCase(round:Round,caseId:string,at=now()):Round{
 const c=round.cases[caseId]
 if(!c?.firstBlindChoice||c.revealedAt||!round.practice&&!Object.values(round.cases).every(entry=>!!entry.firstBlindChoice))return round
 return {...round,cases:{...round.cases,[caseId]:{...c,revealedAt:at}}}
}
export function setPractice(round:Round,practice:boolean):Round{return round.startedAt||Object.values(round.cases).some(c=>c.firstBlindChoice)?round:{...round,practice}}
export function updateFeedback(round:Round,caseId:string,symptoms:Symptom[],notes:string):Round{
 const c=round.cases[caseId]
 return c?{...round,cases:{...round.cases,[caseId]:{...c,symptoms,notes}}}:round
}
export function archiveRound(store:RoundStore,next:Round):RoundStore{return {...store,history:[...store.history,store.current],current:next}}
export function withPlayerLogs(store:RoundStore,sessionId:string,logs:unknown[]):RoundStore{
 const entry={sessionId,logs:[...logs]},exists=store.playerLogs.some(s=>s.sessionId===sessionId)
 return {...store,playerLogs:exists?store.playerLogs.map(s=>s.sessionId===sessionId?entry:s):[...store.playerLogs,entry]}
}
export function restoreStore(raw:string|null,fresh:Round):RoundStore{
 if(!raw)return {schema:'harbeat.bass-neighbors-rounds.v1',current:fresh,history:[],playerLogs:[]}
 let saved:RoundStore
 try{
  saved=JSON.parse(raw)
  if(saved.schema!=='harbeat.bass-neighbors-rounds.v1'||!Array.isArray(saved.history)||!Array.isArray(saved.playerLogs))throw Error()
  for(const round of [saved.current,...saved.history]){
   if(!round?.id||typeof round.selectionSha256!=='string'||typeof round.practice!=='boolean'||!round.cases||Object.keys(round.cases).length!==6)throw Error()
   const assignments=Object.values(round.cases).map(entry=>{
    if(!entry?.heard||!Array.isArray(entry.votes)||!Array.isArray(entry.symptoms)||typeof entry.notes!=='string')throw Error()
    const modes=letters.map(letter=>entry.mapping?.[letter])
    if(modes.some(mode=>!['reference','stem'].includes(mode))||new Set(modes).size!==2)throw Error()
    const validHeard=(heard:unknown)=>!!heard&&typeof heard==='object'&&Object.entries(heard).every(([letter,time])=>letters.includes(letter as Letter)&&typeof time==='string')
    const validChoice=(choice:unknown)=>['A','B','tie','none'].includes(choice as string)
    if(!validHeard(entry.heard)||entry.choice!==undefined&&!validChoice(entry.choice))throw Error()
    if(entry.firstBlindChoice&&(!validChoice(entry.firstBlindChoice.choice)||typeof entry.firstBlindChoice.at!=='string'||!validHeard(entry.firstBlindChoice.heard)))throw Error()
    if(entry.votes.some(v=>!validChoice(v.choice)||typeof v.at!=='string'||typeof v.afterReveal!=='boolean'||!validHeard(v.heard)))throw Error()
    return modes.join('|')
   })
   if(assignments.filter(m=>m==='reference|stem').length!==3||assignments.filter(m=>m==='stem|reference').length!==3)throw Error()
  }
  if(saved.playerLogs.some(entry=>!entry?.sessionId||!Array.isArray(entry.logs)))throw Error()
 }catch{throw Error('本机记录格式无法读取，已有内容未覆盖。请导出原始记录后再检查。')}
 if(saved.current.selectionSha256!==fresh.selectionSha256)return archiveRound(saved,fresh)
 if(Object.keys(fresh.cases).some(id=>!saved.current.cases[id]))throw Error('本机记录中的固定样例不匹配，已有内容未覆盖。请导出原始记录后再检查。')
 return saved
}
