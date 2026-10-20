import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
function documentHtml(raw:string){
 const esc=(s:string)=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
 const inline=(s:string)=>esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\[([^\]]+)\]\((https:\/\/[^\s)]+)\)/g,'<a href="$2">$1</a>')
 let table=false,first=false,out=''
 for(const line of raw.split('\n')){
  if(line.startsWith('|')){if(/^\|[\s|:-]+\|$/.test(line))continue;if(!table){out+='<div class="table"><table><tbody>';table=true;first=true}const tag=first?'th':'td';out+='<tr>'+line.split('|').slice(1,-1).map(v=>`<${tag}>${inline(v.trim())}</${tag}>`).join('')+'</tr>';first=false;continue}
  if(table){out+='</tbody></table></div>';table=false}
  if(line.startsWith('# '))out+='<h1>'+inline(line.slice(2))+'</h1>'
  else if(line.startsWith('## '))out+='<h2>'+inline(line.slice(3))+'</h2>'
  else if(line.startsWith('- '))out+='<p>• '+inline(line.slice(2))+'</p>'
  else if(line.trim())out+='<p>'+inline(line)+'</p>'
 }
 if(table)out+='</tbody></table></div>'
 return '<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HarBeat 混音判断标准 v1.0</title><style>body{margin:0;background:#f7f7ef;color:#29372c;font:16px/1.9 system-ui,sans-serif}main{max-width:960px;padding:24px;margin:auto}a{color:inherit}h1{line-height:1.35;font-size:32px}h2{margin-top:40px;font-size:24px}.table{overflow:auto}table{border-collapse:collapse;min-width:600px}th,td{padding:12px;text-align:left;border:1px solid #cbd3bf;vertical-align:top}code{overflow-wrap:anywhere;font-size:.9em;background:#e6ebdb;padding:2px 4px}@media(max-width:640px){main{padding:16px}h1{font-size:28px}}</style><main><a href="./">返回指标混音</a>'+out+'</main></html>'
}
export default defineConfig({plugins:[react(),{name:'metric-standards',closeBundle(){fs.copyFileSync('dist-metric-mix/metric-mix.html','dist-metric-mix/index.html');fs.writeFileSync('dist-metric-mix/standards.html',documentHtml(fs.readFileSync('../docs/metric-mix-standards-20261020.md','utf8')))}}],base:'./',build:{outDir:'dist-metric-mix',rollupOptions:{input:'metric-mix.html'}},server:{host:'127.0.0.1',port:5213,strictPort:true,proxy:{'/listen':{target:'https://8.136.120.255',changeOrigin:true,secure:true,headers:{origin:'https://8.136.120.255'}}}}})
