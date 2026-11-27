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
  useFlowContext: () => ({ activeFlow: { id: 'f1', name: 'Welcome', status: 'draft' }, hasUnsavedChanges: false }),
}));
vi.mock('@/contexts/ModalContext', () => ({ ModalProvider: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('@/components/FlowsHeaderActions', () => ({ FlowsHeaderActions: () => <button>Save</button> }));
vi.mock('@/components/shortcuts/ShortcutsHelpContext', () => ({
  ShortcutsHelpProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('@/pages/FlowCanvasPage', () => ({
  FlowCanvasPage: () => <Link to="/providers">Open AI Providers</Link>,
}));

const get = vi.fn();
const post = vi.fn();
vi.mock('@/lib/frappe-sdk', () => ({ call: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) } }));
vi.mock('@/services/flowService', () => ({ flowService: { cacheDefinition: vi.fn() } }));
vi.mock('@/hooks/flow/useFlowPermissions', () => ({ useFlowPermissions: () => ({ canManage: true }) }));

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
  await waitFor(() => expect(screen.queryByTestId(/^embed-/)).toBeTruthy());
  return router;
}

describe('embed flow route', () => {
  beforeEach(() => {
    vi.resetModules();
    postMessage.mockClear();
    get.mockReset().mockResolvedValue({ message: { version: 3 } });
    post.mockReset().mockResolvedValue({ message: [] });
    window.history.replaceState({}, '', '/huf/embed/flow/f1?app=happiol');
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

  const errors = () => postMessage.mock.calls.filter(([m]) => m.type === 'guest.error').map(([m]) => m.payload);

  it('reports the loaded flow', async () => {
    await open();
    expect(postMessage.mock.calls).toEqual([
      [{ ns: 'huf.flow.embed', v: 1, type: 'guest.loaded', payload: { flow_id: 'f1', version: 3, status: 'Draft', can_write: true } }, HOST],
    ]);
  });

  it.each([
    ['a missing flow', () => get.mockRejectedValue({ httpStatus: 404 }), 'embed-not-found', 'not_found'],
    ['an app that is not installed', () => post.mockRejectedValue({ exc_type: 'ValidationError' }), 'embed-unknown-app', 'unknown_app'],
    ['a flow that fails to load', () => get.mockRejectedValue({ httpStatus: 500 }), 'embed-load-failed', 'load_failed'],
  ])('shows %s', async (_name, arrange, testId, code) => {
    arrange();
    await open();
    expect(screen.getByTestId(testId)).toBeTruthy();
    expect(errors()).toEqual([{ code, flow_id: 'f1' }]);
  });

  it('rejects a URL without a usable app', async () => {
    window.history.replaceState({}, '', '/huf/embed/flow/f1');
    await open();
    expect(screen.getByTestId('embed-unknown-app')).toBeTruthy();
  });

  it('does not cache a failed palette load, so Retry asks again', async () => {
    post.mockRejectedValueOnce({ httpStatus: 500 });
    await open();
    await act(async () => screen.getByText('Retry').click());
    await waitFor(() => expect(screen.getByTestId('embed-flow-editor')).toBeTruthy());
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('reports a leaving link to the host instead of navigating', async () => {
    const router = await open();
    postMessage.mockClear();
    await act(async () => screen.getByText('Open AI Providers').click());
    await waitFor(() => expect(postMessage).toHaveBeenCalled());
    expect(router.state.location.pathname).toBe('/huf/embed/flow/f1');
    expect(postMessage.mock.calls).toEqual([
      [{ ns: 'huf.flow.embed', v: 1, type: 'guest.navigate', payload: { target: 'providers' } }, HOST],
    ]);
  });

  it('shows the signed-out state on session loss and does not change window.location', async () => {
    await open();
    postMessage.mockClear();
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
