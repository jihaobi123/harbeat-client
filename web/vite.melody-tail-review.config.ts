import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'melody-tail-review-pack',closeBundle(){fs.copyFileSync('melody-tail-review-data.json','dist-melody-tail-review/melody-tail-review-data.json');fs.cpSync('melody-yield-audio','dist-melody-tail-review/melody-yield-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-melody-tail-review',rollupOptions:{input:'melody-tail-review.html'}},server:{host:'127.0.0.1',port:5199,strictPort:true}})
