import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'melody-yield-pack',closeBundle(){fs.copyFileSync('melody-yield-data.json','dist-melody-yield/melody-yield-data.json');fs.cpSync('melody-yield-audio','dist-melody-yield/melody-yield-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-melody-yield',rollupOptions:{input:'melody-yield.html'}},server:{host:'127.0.0.1',port:5198,strictPort:true}})
