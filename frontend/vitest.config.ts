import path from 'path';
import { defineConfig } from 'vitest/config';

// NODE_ENV can be exported as 'production' by the shell in this repo's dev
// environment, which makes npm/yarn skip devDependencies and makes React load
// its production build (breaks @testing-library's act()). Force it for the
// vitest process regardless of the ambient shell env.
process.env.NODE_ENV = 'test';

export default defineConfig({
	test: {
		// Default stays 'node' for fast pure-logic tests (parsers, adapters).
		// Component tests opt into jsdom individually via a per-file
		// `// @vitest-environment jsdom` docblock instead of paying the DOM
		// setup cost on every test file.
		environment: 'node',
		include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
		setupFiles: ['./vitest.setup.ts'],
	},
	resolve: {
		alias: {
			'@': path.resolve(__dirname, './src'),
		},
	},
});
