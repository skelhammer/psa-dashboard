import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        // Use 127.0.0.1 explicitly: on Node 18+ Windows, "localhost" can
        // resolve to ::1 first, and uvicorn binds only to IPv4 by default,
        // which produces AggregateError [ECONNREFUSED] in the proxy.
        target: 'http://127.0.0.1:8880',
        changeOrigin: true,
      },
    },
  },
})
