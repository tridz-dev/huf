import path from 'path';
import react from '@vitejs/plugin-react';
import proxyOptions from './proxyOptions';
import { defineConfig } from 'vite';


/**
 * index.html carries Jinja placeholders that huf/www/huf.py fills in production.
 * The dev server serves the file raw, so `JSON.parse({{ boot }})` was a syntax
 * error ("Unexpected token '{'") on every full reload. Fill them with inert values in dev.
 */
const devTemplatePlaceholders = () => ({
  name: 'huf-dev-template-placeholders',
  apply: 'serve' as const,
  transformIndexHtml: (html: string) =>
    html
      .replace('{{ boot }}', JSON.stringify('{}'))
      .replace('{{ csrf_token }}', 'dev')
      .replace('{{ app_name }}', 'huf'),
});

export default defineConfig({
  base: '/assets/huf/frontend/',
  plugins: [
    react(),
    devTemplatePlaceholders(),
    // VitePWA removed to prevent aggressive caching
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
