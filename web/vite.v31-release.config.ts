import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({plugins:[react()],base:'./',build:{outDir:'dist-v31-release',rollupOptions:{input:'v31-release.html'}},server:{host:'127.0.0.1'}})
