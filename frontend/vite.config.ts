import path from 'path';
import react from '@vitejs/plugin-react';
import proxyOptions from './proxyOptions';
import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  base: '/assets/huf/frontend/',
  plugins: [
    react(),
    VitePWA({
      injectRegister: false,
      // Frappe's www renderer only serves known text extensions raw
      // (frappe.utils.jinja.guess_is_path); .webmanifest is not one of them,
      // so the manifest is emitted as manifest.json instead.
      manifestFilename: 'manifest.json',
      manifest: {
        name: 'Huf',
        short_name: 'Huf',
        description: 'Build and run smart AI agents with tools, chat, and automation.',
        start_url: '/huf/',
        scope: '/huf/',
        display: 'standalone',
        background_color: '#ffffff',
        theme_color: '#111827',
        icons: [
          {
            src: '/assets/huf/frontend/icons/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: '/assets/huf/frontend/icons/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
          },
          {
            src: '/assets/huf/frontend/icons/maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        inlineWorkboxRuntime: true,
        navigateFallback: null,
        skipWaiting: true,
        clientsClaim: true,
        globPatterns: [],
        modifyURLPrefix: {
          '': '/assets/huf/frontend/',
        },
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    target: 'es2022',
    outDir: '../huf/public/frontend',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          ui: ['@radix-ui/react-dialog', '@radix-ui/react-popover', '@radix-ui/react-select', 'lucide-react'],
          recharts: ['recharts'],
          xyflow: ['@xyflow/react', 'reactflow'],
          markdown: ['streamdown', 'mermaid'],
          highlighter: ['prismjs'],
        }
      }
    }
  },
  server: {
    port: 8080,
    proxy: proxyOptions
  },
});
