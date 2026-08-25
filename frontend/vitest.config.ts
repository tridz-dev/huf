import path from 'path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [react()],
	test: {
		// Per-suite default; component tests opt into jsdom via a
		// `// @vitest-environment jsdom` docblock at the top of the file
		// instead of switching this globally, so plain .test.ts logic
		// tests (the existing majority) keep the cheaper node environment.
		environment: 'node',
		include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
		setupFiles: ['./src/setupTests.ts'],
	},
	resolve: {
		alias: {
			'@': path.resolve(__dirname, './src'),
		},
	},
});
