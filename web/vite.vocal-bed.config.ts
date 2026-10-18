import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'vocal-bed-pack',closeBundle(){fs.copyFileSync('vocal-bed-data.json','dist-vocal-bed/vocal-bed-data.json');fs.cpSync('vocal-bed-audio','dist-vocal-bed/vocal-bed-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-vocal-bed',rollupOptions:{input:'vocal-bed.html'}},server:{host:'127.0.0.1',port:5193,strictPort:true}})
