import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'big-step-cut-pack',closeBundle(){fs.copyFileSync('big-step-cut-data.json','dist-big-step-cut/big-step-cut-data.json');fs.cpSync('big-step-cut-audio','dist-big-step-cut/big-step-cut-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-big-step-cut',rollupOptions:{input:'big-step-cut.html'}},server:{host:'127.0.0.1',port:5205,strictPort:true}})
