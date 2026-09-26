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

  // jsdom doesn't implement ResizeObserver, which Radix's Popper (used by
  // Select/Popover/Dropdown, etc.) relies on for positioning. Without this,
  // an interaction that opens a Radix popover can hang indefinitely in CI
  // instead of throwing cleanly, timing out the test rather than failing
  // fast — a no-op polyfill is the documented workaround (same fix Radix's
  // own test suite uses).
  if (typeof globalThis.ResizeObserver === 'undefined') {
    globalThis.ResizeObserver = class ResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
}
