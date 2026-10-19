import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'melody-filter-pack',closeBundle(){fs.copyFileSync('melody-filter-data.json','dist-melody-filter/melody-filter-data.json');fs.cpSync('melody-filter-audio','dist-melody-filter/melody-filter-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-melody-filter',rollupOptions:{input:'melody-filter.html'}},server:{host:'127.0.0.1',port:5206,strictPort:true}})
