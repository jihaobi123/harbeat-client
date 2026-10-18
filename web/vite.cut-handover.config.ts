import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'cut-handover-pack',closeBundle(){fs.copyFileSync('cut-handover-data.json','dist-cut-handover/cut-handover-data.json');fs.cpSync('cut-handover-audio','dist-cut-handover/cut-handover-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-cut-handover',rollupOptions:{input:'cut-handover.html'}},server:{host:'127.0.0.1',port:5202,strictPort:true}})
