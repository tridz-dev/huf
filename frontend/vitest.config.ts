import path from 'path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [react()],
	test: {
		// Default environment stays 'node' for the existing *.test.ts suite (pure
		// logic/mapper tests with no DOM needs). Component tests (*.test.tsx) opt
		// into jsdom per-file via a `// @vitest-environment jsdom` docblock at the
		// top of the file, so the two suites can coexist without a global flip.
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
