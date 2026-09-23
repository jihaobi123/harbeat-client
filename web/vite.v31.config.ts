import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({plugins:[react()],base:'./',build:{outDir:'dist-v31',rollupOptions:{input:'v31.html'}},server:{host:'127.0.0.1'}})
