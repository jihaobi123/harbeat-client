import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'bass-pack',closeBundle(){fs.copyFileSync('bass-swap-data.json','dist-bass-swap/bass-swap-data.json');fs.cpSync('bass-audio','dist-bass-swap/bass-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-bass-swap',rollupOptions:{input:'bass-swap.html'}},server:{host:'127.0.0.1',port:5189,strictPort:true}})
