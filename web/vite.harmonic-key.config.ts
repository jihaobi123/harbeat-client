import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
export default defineConfig({plugins:[react(),{name:'harmonic-pack',closeBundle(){fs.copyFileSync('harmonic-key-data.json','dist-harmonic-key/harmonic-key-data.json')}}],base:'./',build:{outDir:'dist-harmonic-key',rollupOptions:{input:'harmonic-key.html'}},server:{host:'127.0.0.1',port:5187,strictPort:true,proxy:{'/listen/':{target:'https://8.136.120.255',changeOrigin:true,secure:true}}}})
