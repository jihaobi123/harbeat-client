import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'combination-single-control-pack',closeBundle(){fs.copyFileSync('combination-single-control-data.json','dist-combination-single-control/combination-single-control-data.json');fs.cpSync('combination-single-control-audio','dist-combination-single-control/combination-single-control-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-combination-single-control',rollupOptions:{input:['combination-single-control.html','combination-single-control-audit.html']}},server:{host:'127.0.0.1',port:5212,strictPort:true}})
