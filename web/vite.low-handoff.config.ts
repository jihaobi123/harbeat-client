import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'low-handoff-pack',closeBundle(){fs.copyFileSync('low-handoff-data.json','dist-low-handoff/low-handoff-data.json');fs.cpSync('low-handoff-audio','dist-low-handoff/low-handoff-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-low-handoff',rollupOptions:{input:'low-handoff.html'}},server:{host:'127.0.0.1',port:5208,strictPort:true}})
