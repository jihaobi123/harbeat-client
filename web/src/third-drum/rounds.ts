import type {Mode} from './policy'
export type {Mode} from './policy'

export const letters=['A','B'] as const
export type Letter=typeof letters[number]
export type Choice=Letter|'tie'|'none'
export type Symptom='beat-clearer'|'beat-worse'|'timing-artifact'|'rhythm-steady'|'drum-late'|'double-vocal'|'space-clearer'|'melody-cut'|'thin'|'voice-clearer'|'bed-switch-obvious'|'voice-overlap'|'voice-cut'|'clicks'|'stem-bleed'|'louder'|'quieter'
export type CaseFeedback={
 mapping:Record<Letter,Mode>;recommendedOrder:Letter[];firstPlayed?:{letter:Letter;at:string};heard:Partial<Record<Letter,string>>
 firstBlindChoice?:{choice:Choice;at:string;heard:Partial<Record<Letter,string>>};choice?:Choice
 votes:{choice:Choice;at:string;afterReveal:boolean;heard:Partial<Record<Letter,string>>}[];revealedAt?:string
 symptoms:Symptom[];notes:string
}
export type Round={id:string;createdAt:string;selectionSha256:string;assetFingerprint?:string;practice:boolean;orderPhase:0|1;startedAt?:string;sourceSnapshot?:unknown;cases:Record<string,CaseFeedback>}
export type RoundStore={schema:'harbeat.third-drum-rounds.v1';current:Round;history:Round[];playerLogs:{sessionId:string;logs:unknown[]}[]}
export const storageKey='harbeat.third-drum.v1.rounds'
const now=()=>new Date().toISOString()
export function createRound(caseIds:string[],selectionSha256:string,practice=false,random=Math.random,createdAt=now(),id:string=crypto.randomUUID(),orderPhase:0|1=0):Round{
 if(caseIds.length<1||caseIds.length>3||new Set(caseIds).size!==caseIds.length)throw Error('第三首鼓片段盲听需要一到三个不同的固定样例')
 return {id,createdAt,selectionSha256,practice,orderPhase,cases:Object.fromEntries(caseIds.map((caseId,i)=>{
  const naturalFirst=random()<.5
  return [caseId,{mapping:naturalFirst?{A:'natural',B:'relay'}:{A:'relay',B:'natural'},recommendedOrder:(i+orderPhase)%2===0?['A','B']:['B','A'],heard:{},votes:[],symptoms:[],notes:''}]
 }))}
}
export function markPlayed(round:Round,event:{roundId?:string;caseId:string;letter?:string;status:string},at=now()):Round{
 const c=round.cases[event.caseId]
 if(event.status!=='playing'||event.roundId!==round.id||!c||c.firstPlayed||!letters.includes(event.letter as Letter))return round
 return {...round,cases:{...round.cases,[event.caseId]:{...c,firstPlayed:{letter:event.letter as Letter,at}}}}
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
 if(!raw)return {schema:'harbeat.third-drum-rounds.v1',current:fresh,history:[],playerLogs:[]}
 let saved:RoundStore
 try{
  saved=JSON.parse(raw)
  if(saved.schema!=='harbeat.third-drum-rounds.v1'||!Array.isArray(saved.history)||!Array.isArray(saved.playerLogs))throw Error()
  for(const round of [saved.current,...saved.history]){
   if(!round?.id||typeof round.selectionSha256!=='string'||typeof round.practice!=='boolean'||!round.cases||![1,2,3].includes(Object.keys(round.cases).length)||![0,1].includes(round.orderPhase))throw Error()
   Object.values(round.cases).forEach((entry,i)=>{
    if(!entry?.heard||!Array.isArray(entry.votes)||!Array.isArray(entry.symptoms)||typeof entry.notes!=='string')throw Error()
    const modes=letters.map(letter=>entry.mapping?.[letter])
    if(modes.some(mode=>!['natural','relay'].includes(mode))||new Set(modes).size!==2)throw Error()
    const validHeard=(heard:unknown)=>!!heard&&typeof heard==='object'&&Object.entries(heard).every(([letter,time])=>letters.includes(letter as Letter)&&typeof time==='string')
    const validChoice=(choice:unknown)=>['A','B','tie','none'].includes(choice as string)
    if(!validHeard(entry.heard)||entry.choice!==undefined&&!validChoice(entry.choice))throw Error()
    if(entry.firstBlindChoice&&(!validChoice(entry.firstBlindChoice.choice)||typeof entry.firstBlindChoice.at!=='string'||!validHeard(entry.firstBlindChoice.heard)))throw Error()
    if(entry.votes.some(v=>!validChoice(v.choice)||typeof v.at!=='string'||typeof v.afterReveal!=='boolean'||!validHeard(v.heard)))throw Error()
    const expected=(i+round.orderPhase)%2===0?['A','B']:['B','A']
    if(!Array.isArray(entry.recommendedOrder)||entry.recommendedOrder.join('|')!==expected.join('|'))throw Error()
    if(entry.firstPlayed&&(!letters.includes(entry.firstPlayed.letter)||typeof entry.firstPlayed.at!=='string'))throw Error()
   })
  }
  if(saved.playerLogs.some(entry=>!entry?.sessionId||!Array.isArray(entry.logs)))throw Error()
 }catch{throw Error('本机记录格式无法读取，已有内容未覆盖。请导出原始记录后再检查。')}
 if(saved.current.selectionSha256!==fresh.selectionSha256||saved.current.assetFingerprint!==fresh.assetFingerprint)return archiveRound(saved,fresh)
 if(Object.keys(fresh.cases).some(id=>!saved.current.cases[id]))throw Error('本机记录中的固定样例不匹配，已有内容未覆盖。请导出原始记录后再检查。')
 return saved
}
