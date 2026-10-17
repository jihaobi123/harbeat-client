import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'melody-pack',closeBundle(){fs.copyFileSync('melody-overlap-data.json','dist-melody-overlap/melody-overlap-data.json');fs.cpSync('melody-audio','dist-melody-overlap/melody-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-melody-overlap',rollupOptions:{input:'melody-overlap.html'}},server:{host:'127.0.0.1',port:5188,strictPort:true}})
