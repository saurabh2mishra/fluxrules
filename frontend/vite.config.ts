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
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router-dom')) {
            return 'react-vendor';
          }
          if (id.includes('@tanstack/react-query')) return 'query-vendor';
          if (id.includes('@radix-ui')) return 'ui-vendor';
          if (id.includes('react-hook-form') || id.includes('@hookform') || id.includes('zod')) return 'form-vendor';
          if (id.includes('lucide-react')) return 'icons';
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
})
