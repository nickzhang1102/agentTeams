import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  },
  build: {
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return
          }

          if (id.includes('html2pdf.js')) {
            return 'html2pdf'
          }

          if (id.includes('html2canvas')) {
            return 'html2canvas'
          }

          if (id.includes('marked')) {
            return 'marked'
          }

          if (id.includes('highlight.js')) {
            return 'highlight'
          }

          if (id.includes('dompurify')) {
            return 'dompurify'
          }

          if (id.includes('@element-plus/icons-vue')) {
            return 'element-plus-icons'
          }

          if (id.includes('element-plus/es/components/')) {
            const match = id.match(/element-plus\/es\/components\/([^/]+)/)
            if (match?.[1]) {
              return `el-${match[1]}`
            }
          }

          if (id.includes('element-plus')) {
            return 'element-plus-core'
          }

          if (id.includes('d3')) {
            return 'd3'
          }

          if (id.includes('vue') || id.includes('pinia') || id.includes('vue-router')) {
            return 'vue-vendor'
          }
        }
      }
    }
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true
      },
      '/static': {
        target: 'http://localhost:5000',
        changeOrigin: true
      }
    }
  }
})
