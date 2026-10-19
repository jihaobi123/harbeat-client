import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'third-drum-pack',closeBundle(){fs.copyFileSync('third-drum-data.json','dist-third-drum/third-drum-data.json');fs.cpSync('third-drum-audio','dist-third-drum/third-drum-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-third-drum',rollupOptions:{input:'third-drum.html'}},server:{host:'127.0.0.1',port:5209,strictPort:true}})
