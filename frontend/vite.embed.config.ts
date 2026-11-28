import { defineConfig } from 'vite';

/** The host-page bundle for `<huf-flow-builder>`: one file with a stable name, at /assets/huf/embed/. */
export default defineConfig({
  publicDir: false,
  build: {
    target: 'es2022',
    outDir: '../huf/public/embed',
    emptyOutDir: true,
    lib: { entry: 'src/embed/huf-flow-builder.ts', formats: ['es'], fileName: () => 'huf-flow-builder.js' },
  },
});
