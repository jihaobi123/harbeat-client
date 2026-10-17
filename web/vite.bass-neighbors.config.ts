import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'bass-neighbors-pack',closeBundle(){fs.copyFileSync('bass-neighbors-data.json','dist-bass-neighbors/bass-neighbors-data.json');fs.cpSync('neighbor-audio','dist-bass-neighbors/neighbor-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-bass-neighbors',rollupOptions:{input:'bass-neighbors.html'}},server:{host:'127.0.0.1',port:5191,strictPort:true}})
