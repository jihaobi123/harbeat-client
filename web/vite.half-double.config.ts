import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'half-double-pack',closeBundle(){fs.copyFileSync('half-double-data.json','dist-half-double/half-double-data.json');fs.cpSync('half-double-audio','dist-half-double/half-double-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-half-double',rollupOptions:{input:'half-double.html'}},server:{host:'127.0.0.1',port:5204,strictPort:true}})
