// Global vitest setup, loaded for every test file (node and jsdom alike).
// Component tests still opt into jsdom per-file via a `// @vitest-environment
// jsdom` docblock; guard on `document` so this is a no-op for the majority
// of plain-logic .test.ts files that run under the node environment.
import { afterEach } from 'vitest';

if (typeof document !== 'undefined') {
  const { cleanup } = await import('@testing-library/react');
  await import('@testing-library/jest-dom/vitest');
  afterEach(() => {
    cleanup();
  });
}
