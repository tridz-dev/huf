import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// React Testing Library only auto-registers its afterEach(cleanup) when it
// detects Jest globals; under vitest that detection doesn't fire, so without
// this, DOM nodes from earlier tests/renders in the same file (or the same
// it.each block) accumulate and getByText starts matching multiple elements.
afterEach(() => {
	cleanup();
});
