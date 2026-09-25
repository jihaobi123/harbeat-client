/** Bind the entire frozen selection: sources, cues, rates and render lengths. */
export function assertSelectionBinding(renderedHash:unknown,selectedHash:string){
 if(typeof renderedHash!=='string'||!/^[0-9a-f]{64}$/.test(renderedHash)||renderedHash!==selectedHash)throw Error('选点或源文件已改变，必须重新准备分轨片段')
}
