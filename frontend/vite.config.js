import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    // 프론트와 API를 한 오리진으로 — 터널/역방향프록시 환경에서 그대로 동작
    proxy: {
      '/api': 'http://localhost:8000',
    },
    // cloudflared quick tunnel 공개 주소 허용
    allowedHosts: ['.trycloudflare.com'],
  },
})
