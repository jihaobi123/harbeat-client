import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'rhythm-bridge-pack',closeBundle(){fs.copyFileSync('rhythm-bridge-data.json','dist-rhythm-bridge/rhythm-bridge-data.json');fs.cpSync('rhythm-bridge-audio','dist-rhythm-bridge/rhythm-bridge-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-rhythm-bridge',rollupOptions:{input:'rhythm-bridge.html'}},server:{host:'127.0.0.1',port:5200,strictPort:true}})
