import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'vocal-echo-solo-pack',closeBundle(){fs.copyFileSync('vocal-echo-solo-data.json','dist-vocal-echo-solo/vocal-echo-solo-data.json');fs.cpSync('vocal-echo-solo-audio','dist-vocal-echo-solo/vocal-echo-solo-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-vocal-echo-solo',rollupOptions:{input:'vocal-echo-solo.html'}},server:{host:'127.0.0.1',port:5201,strictPort:true}})
