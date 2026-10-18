import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'vocal-handover-pack',closeBundle(){fs.copyFileSync('vocal-handover-data.json','dist-vocal-handover/vocal-handover-data.json');fs.cpSync('vocal-handover-audio','dist-vocal-handover/vocal-handover-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-vocal-handover',rollupOptions:{input:'vocal-handover.html'}},server:{host:'127.0.0.1',port:5197,strictPort:true}})
