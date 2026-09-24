import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({plugins:[react()],base:'./',build:{outDir:'dist-vocal-overlap',rollupOptions:{input:'vocal-overlap.html'}},server:{host:'127.0.0.1'}})
