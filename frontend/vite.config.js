import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Proxy /api to the FastAPI backend so the frontend can use same-origin fetches.
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
