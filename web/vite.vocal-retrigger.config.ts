import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'vocal-retrigger-pack',closeBundle(){fs.copyFileSync('vocal-retrigger-data.json','dist-vocal-retrigger/vocal-retrigger-data.json');fs.cpSync('vocal-retrigger-audio','dist-vocal-retrigger/vocal-retrigger-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-vocal-retrigger',rollupOptions:{input:'vocal-retrigger.html'}},server:{host:'127.0.0.1',port:5207,strictPort:true}})
