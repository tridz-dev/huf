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

// Node >= 25 ships an experimental global Web Storage that shadows jsdom's
// localStorage/sessionStorage (and is undefined without --localstorage-file).
// Point the globals at the jsdom window's storage so tests behave the same on
// any Node version.
if (typeof document !== 'undefined') {
  const jsdomWindow = (globalThis as { jsdom?: { window: Window } }).jsdom?.window;
  if (jsdomWindow) {
    for (const key of ['localStorage', 'sessionStorage'] as const) {
      Object.defineProperty(globalThis, key, {
        configurable: true,
        get: () => jsdomWindow[key],
      });
    }
  }
}
