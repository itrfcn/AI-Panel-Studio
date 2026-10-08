import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Vite 配置
// - 默认端口 5173
// - 代理 /api 到后端 FastAPI（8000），便于前后端联调
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
