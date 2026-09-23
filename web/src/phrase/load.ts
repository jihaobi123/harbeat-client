/** Gzip snapshots avoid repeatedly transferring the full evidence JSON over the relay. */
export async function loadJson(file:string,base:URL){
 if(file!=='cases.json'&&typeof DecompressionStream!=='undefined'){
  const r=await fetch(new URL(file+'.gz',base))
  if(r.ok&&r.body)return new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).json()
 }
 const r=await fetch(new URL(file,base));if(!r.ok)throw Error(`${file} 加载失败：${r.status}`);return r.json()
}
