import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'bass-generalization-pack',closeBundle(){fs.copyFileSync('bass-generalization-data.json','dist-bass-generalization/bass-generalization-data.json');fs.cpSync('coverage-audio','dist-bass-generalization/coverage-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-bass-generalization',rollupOptions:{input:'bass-generalization.html'}},server:{host:'127.0.0.1',port:5190,strictPort:true}})
