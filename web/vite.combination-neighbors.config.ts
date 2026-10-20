import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'combination-neighbors-pack',closeBundle(){fs.copyFileSync('combination-neighbors-data.json','dist-combination-neighbors/combination-neighbors-data.json');fs.cpSync('combination-neighbors-audio','dist-combination-neighbors/combination-neighbors-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-combination-neighbors',rollupOptions:{input:['combination-neighbors.html','combination-neighbors-audit.html']}},server:{host:'127.0.0.1',port:5211,strictPort:true}})
