import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'drum-loop-pack',closeBundle(){fs.copyFileSync('drum-loop-data.json','dist-drum-loop/drum-loop-data.json');fs.cpSync('drum-loop-audio','dist-drum-loop/drum-loop-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-drum-loop',rollupOptions:{input:'drum-loop.html'}},server:{host:'127.0.0.1',port:5192,strictPort:true}})
