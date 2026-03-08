import path from 'path';
import react from '@vitejs/plugin-react';
import proxyOptions from './proxyOptions';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [
    react({
      babel: {
        parserOpts: {
          plugins: ['typescript', 'jsx']
        },
        plugins: [
          [
            'babel-plugin-transform-imports',
            {
              'lucide-react': {
                transform: 'lucide-react/dist/esm/icons/${member}',
                preventFullImport: true,
                kebabCase: true,
              },
            },
          ],
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: '../huf/public/frontend',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          ui: ['@radix-ui/react-dialog', '@radix-ui/react-popover', '@radix-ui/react-select', 'lucide-react'],
          charts: ['recharts', '@xyflow/react'],
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
