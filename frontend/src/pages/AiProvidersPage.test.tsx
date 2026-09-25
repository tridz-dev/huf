// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';

vi.mock('@/services/providerApi', async () => {
  const actual = await vi.importActual<typeof import('@/services/providerApi')>(
    '@/services/providerApi',
  );
  return {
    ...actual,
    getProviders: vi.fn().mockResolvedValue({ items: [], hasMore: false, total: 0 }),
    getModels: vi.fn().mockResolvedValue([]),
    getProvider: vi.fn(),
    createProvider: vi.fn(),
    updateProvider: vi.fn(),
    deleteProvider: vi.fn(),
    testProviderConnection: vi.fn(),
  };
});

vi.mock('@/services/subscriptionRuntimeApi', () => ({
  testSubscriptionRuntimeConnection: vi.fn(),
}));

vi.mock('@/lib/frappe-sdk', () => ({
  db: {
    getDocList: vi.fn().mockResolvedValue([
      { name: 'SR-0001', runtime_name: 'Claude Code (local)' },
    ]),
    getDoc: vi.fn(),
    createDoc: vi.fn(),
    updateDoc: vi.fn(),
    deleteDoc: vi.fn(),
  },
  call: { post: vi.fn(), get: vi.fn() },
  auth: {},
}));

import { AiProvidersPage } from './AiProvidersPage';

// jsdom doesn't implement pointer capture / scrollIntoView, which Radix's
// Select popper relies on — polyfill just enough for user-event clicks to
// work, same workaround Radix's own test suite documents.
beforeEach(() => {
  Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
  Element.prototype.setPointerCapture = Element.prototype.setPointerCapture ?? (() => {});
  Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture ?? (() => {});
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
});

describe('AiProvidersPage — Subscription CLI provider mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('hides API key/base URL fields and shows the runtime picker when Subscription CLI is selected', async () => {
    const user = userEvent.setup();

    render(
      <BrowserRouter>
        <AiProvidersPage addProviderKey={1} />
      </BrowserRouter>,
    );

    // Dialog opens on mount (addProviderKey > 0) — API mode is the default.
    expect(await screen.findByLabelText(/API Key/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/API Base URL/i)).toBeInTheDocument();
    expect(screen.queryByText(/Subscription Runtime/i)).not.toBeInTheDocument();

    // Switch Provider Mode to "Subscription CLI".
    await user.click(screen.getByRole('combobox', { name: /provider mode/i }));
    await user.click(await screen.findByRole('option', { name: 'Subscription CLI' }));

    // API key / base URL fields are hidden; the runtime picker and billing
    // mode label appear instead.
    await waitFor(() => {
      expect(screen.queryByLabelText(/^API Key/i)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/API Base URL/i)).not.toBeInTheDocument();
    });
    expect(screen.getAllByText(/Subscription Runtime/i).length).toBeGreaterThan(0);
    expect(screen.getByText('Subscription')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /test runtime/i })).toBeInTheDocument();
  });
});
