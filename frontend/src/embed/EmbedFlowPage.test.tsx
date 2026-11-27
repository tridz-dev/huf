// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, act } from '@testing-library/react';
import { createMemoryRouter, Link, RouterProvider } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/UserContext', () => ({ useUser: () => ({ isLoading: false, isAuthenticated: true }) }));
vi.mock('@/contexts/PermissionsContext', () => ({
  usePermissions: () => ({ isLoading: false, hasCapability: () => true }),
}));
vi.mock('@/contexts/FlowContext', () => ({
  FlowProvider: ({ children }: { children: React.ReactNode }) => children,
  useFlowContext: () => ({ activeFlow: { name: 'Welcome' } }),
}));
vi.mock('@/contexts/ModalContext', () => ({ ModalProvider: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('@/components/FlowsHeaderActions', () => ({ FlowsHeaderActions: () => <button>Save</button> }));
vi.mock('@/components/shortcuts/ShortcutsHelpContext', () => ({
  ShortcutsHelpProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('@/pages/FlowCanvasPage', () => ({
  FlowCanvasPage: () => <Link to="/providers">Open AI Providers</Link>,
}));

const HOST = 'https://host.example';
const postMessage = vi.fn();
const originalParent = window.parent;

function setBoot(boot: object) {
  (window as unknown as { frappe: object }).frappe = { boot };
}

async function open(path = '/embed/flow/f1?app=happiol') {
  const { default: EmbedFlowPage } = await import('./EmbedFlowPage');
  const router = createMemoryRouter([{ path: '/embed/flow/:flowId', element: <EmbedFlowPage /> }], {
    basename: '/huf',
    initialEntries: [`/huf${path}`],
  });
  render(<RouterProvider router={router} />);
  return router;
}

describe('embed flow route', () => {
  beforeEach(() => {
    vi.resetModules();
    postMessage.mockClear();
    window.history.replaceState({}, '', '/huf/embed/flow/f1');
    Object.defineProperty(window, 'parent', { configurable: true, value: { postMessage } });
    setBoot({ huf_embed: { allowed_origins: [HOST, '*'] } });
  });
  afterEach(() => {
    cleanup();
    Object.defineProperty(window, 'parent', { configurable: true, value: originalParent });
  });

  it('renders the editor without app chrome', async () => {
    await open();
    expect(screen.getByTestId('embed-flow-editor')).toBeTruthy();
    expect(document.querySelector('[data-sidebar]')).toBeNull();
  });

  it('refuses to render without the server embed boot data', async () => {
    setBoot({});
    await open();
    expect(screen.getByTestId('embed-not-permitted')).toBeTruthy();
  });

  it('reports a leaving link to the host instead of navigating', async () => {
    const router = await open();
    await act(async () => screen.getByText('Open AI Providers').click());
    await waitFor(() => expect(postMessage).toHaveBeenCalled());
    expect(router.state.location.pathname).toBe('/huf/embed/flow/f1');
    expect(postMessage.mock.calls).toEqual([
      [{ ns: 'huf.flow.embed', v: 1, type: 'guest.navigate', payload: { target: 'providers' } }, HOST],
    ]);
  });

  it('shows the signed-out state on session loss and does not change window.location', async () => {
    await open();
    const { leaveForLogin } = await import('@/lib/sessionInvalidation');
    const before = window.location.href;
    act(() => {
      expect(leaveForLogin('/login?redirect-to=x')).toBe(false);
      leaveForLogin('/login?redirect-to=x');
    });
    expect(screen.getByTestId('embed-signed-out')).toBeTruthy();
    expect(window.location.href).toBe(before);
    expect(postMessage.mock.calls).toEqual([
      [{ ns: 'huf.flow.embed', v: 1, type: 'guest.error', payload: { code: 'session_expired' } }, HOST],
    ]);
  });

  it('keeps links to runs of this flow in the frame and sends other flows to the host', async () => {
    const { classifyEmbedNavigation } = await import('./navigation');
    const here = { pathname: '/embed/flow/f1', search: '?app=happiol' };
    expect(classifyEmbedNavigation(here, { pathname: '/flows/f1', search: '?run=R1' })).toEqual({
      kind: 'rewrite',
      to: '/embed/flow/f1?app=happiol&run=R1',
    });
    expect(classifyEmbedNavigation(here, { pathname: '/flows/f2', search: '' })).toEqual({
      kind: 'leave',
      target: 'flow_list',
    });
    expect(classifyEmbedNavigation(here, { pathname: '/embed/flow/f1', search: '' })).toEqual({ kind: 'stay' });
  });
});
