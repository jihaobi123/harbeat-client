import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'combination-pack',closeBundle(){fs.copyFileSync('combination-step-one-data.json','dist-combination-step-one/combination-step-one-data.json');fs.cpSync('combination-step-one-audio','dist-combination-step-one/combination-step-one-audio',{recursive:true})}}],base:'./',build:{outDir:'dist-combination-step-one',rollupOptions:{input:['combination-step-one.html','combination-audit.html']}},server:{host:'127.0.0.1',port:5210,strictPort:true}})
