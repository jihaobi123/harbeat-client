import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'vocal-echo-pack',closeBundle(){fs.copyFileSync('vocal-echo-data.json','dist-vocal-echo/vocal-echo-data.json');fs.cpSync('vocal-echo-audio','dist-vocal-echo/vocal-echo-audio',{recursive:true});fs.cpSync('vocal-endpoints-audio','dist-vocal-echo/vocal-endpoints-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-vocal-echo',rollupOptions:{input:'vocal-echo.html'}},server:{host:'127.0.0.1',port:5196,strictPort:true}})
