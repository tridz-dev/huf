// Global Vitest setup file (wired via `test.setupFiles` in vitest.config.ts).
//
// This only registers `@testing-library/jest-dom`'s custom `expect` matchers
// (e.g. `toBeInTheDocument`, `toHaveClass`). Registering matchers has no
// runtime dependency on a DOM being present, so this is safe to load for the
// existing Node-environment `*.test.ts` suite as well as the jsdom-environment
// `*.test.tsx` component suite — it never accesses `document`/`window` itself.
import '@testing-library/jest-dom/vitest';
