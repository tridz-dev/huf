import path from 'path';
import react from '@vitejs/plugin-react';
import proxyOptions from './proxyOptions';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build:{
    outDir: '../agentflo/public/frontend',
    emptyOutDir: true,
  },
  server: {
    port: 8080,
    proxy: proxyOptions
  },
});
