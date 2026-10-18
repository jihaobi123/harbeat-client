import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'vocal-endpoints-pack',closeBundle(){fs.copyFileSync('vocal-endpoints-data.json','dist-vocal-endpoints/vocal-endpoints-data.json');fs.cpSync('vocal-endpoints-audio','dist-vocal-endpoints/vocal-endpoints-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-vocal-endpoints',rollupOptions:{input:'vocal-endpoints.html'}},server:{host:'127.0.0.1',port:5194,strictPort:true}})
