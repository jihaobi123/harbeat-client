import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'bed-gap-pack',closeBundle(){fs.copyFileSync('bed-gap-data.json','dist-bed-gap/bed-gap-data.json');fs.cpSync('bed-gap-audio','dist-bed-gap/bed-gap-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-bed-gap',rollupOptions:{input:'bed-gap.html'}},server:{host:'127.0.0.1',port:5203,strictPort:true}})
