// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const SENTINEL = 'SENTINEL-9f3a+919999000000';

vi.mock('@/contexts/UserContext', () => ({ useUser: () => ({ isLoading: false, isAuthenticated: true }) }));
// An app-only user: no Huf capability at all.
vi.mock('@/contexts/PermissionsContext', async () => {
  const { createContext, useContext } = await import('react');
  const PermissionsContext = createContext<unknown>(undefined);
  return {
    PermissionsContext,
    usePermissions: () => (useContext(PermissionsContext) as object | undefined) ?? { isLoading: false, hasCapability: () => false },
  };
});
vi.mock('@/contexts/FlowContext', () => ({
  FlowProvider: ({ children }: { children: React.ReactNode }) => children,
  useFlowContext: () => ({
    activeFlow: { id: 'f1', name: `Welcome ${SENTINEL}`, status: 'draft', nodes: [] },
    hasUnsavedChanges: false,
    saveState: 'idle',
  }),
}));
vi.mock('@/contexts/ModalContext', () => ({ ModalProvider: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('@/components/FlowsHeaderActions', () => ({ FlowsHeaderActions: () => <button data-testid="flow-publish">Publish</button> }));
vi.mock('@/components/shortcuts/ShortcutsHelpContext', () => ({
  ShortcutsHelpProvider: ({ children }: { children: React.ReactNode }) => children,
}));
// Seeded links a panel could render: a Huf screen, a desk run form and the flow definition form.
vi.mock('@/pages/FlowCanvasPage', () => ({
  FlowCanvasPage: () => (
    <div>
      <a href="/huf/flows">Huf flows</a>
      <a href="/app/agent-flow-run/RUN-1">Run form</a>
      <a href="/app/flow-definition/f1">Flow form</a>
      <a href="/huf/executions?tab=approvals">Approvals</a>
      <a href={`/huf/agents/${SENTINEL}`}>Agent</a>
    </div>
  ),
}));
const panels: Array<[string, string]> = [];
vi.mock('@/components/FlowRunHistory', () => ({
  FlowRunHistory: ({ flowId, open }: { flowId: string; open: boolean }) => {
    if (open) panels.push(['runs', flowId]);
    return null;
  },
}));
vi.mock('@/components/flow/members/FlowMembersPanel', () => ({
  FlowMembersPanel: ({ flowId, open }: { flowId: string; open: boolean }) => {
    if (open) panels.push(['people', flowId]);
    return null;
  },
}));
vi.mock('@/components/FlowRunViewer', () => ({ FlowRunViewer: () => null }));
vi.mock('@/components/flow/RunFlowDialog', () => ({
  RunFlowDialog: ({ open, testOnly }: { open: boolean; testOnly?: boolean }) =>
    open ? <div data-testid="run-dialog" data-test-only={String(!!testOnly)} /> : null,
}));
vi.mock('@/components/flow/header/useFlowHeaderActions', () => ({
  useFlowHeaderActions: () => ({
    handleSaveDraft: vi.fn(),
    handleRun: vi.fn(),
    startRun: vi.fn(),
    showRunDialog: false,
    setShowRunDialog: vi.fn(),
  }),
}));

const get = vi.fn();
const post = vi.fn();
vi.mock('@/lib/frappe-sdk', () => ({ call: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) } }));
vi.mock('@/services/flowService', () => ({ flowService: { cacheDefinition: vi.fn() } }));

const HOST = 'https://host.example';
const postMessage = vi.fn();
const originalParent = window.parent;
const POLICY = { publish: 'host', test: 'dry_run', can_edit: true, can_test: true, can_approve: true };

function setBoot(policy: object | undefined) {
  (window as unknown as { frappe: object }).frappe = { boot: { huf_embed: { allowed_origins: [HOST], policy } } };
}

async function open() {
  const { default: EmbedFlowPage } = await import('./EmbedFlowPage');
  const router = createMemoryRouter([{ path: '/embed/flow/:flowId', element: <EmbedFlowPage /> }], {
    basename: '/huf',
    initialEntries: ['/huf/embed/flow/f1?app=happiol'],
  });
  render(<RouterProvider router={router} />);
  await waitFor(() => expect(screen.queryAllByTestId(/^embed-/).length).toBeGreaterThan(0));
  return router;
}

const navigations = () => postMessage.mock.calls.filter(([m]) => m.type === 'guest.navigate').map(([m]) => m.payload);

describe('embed policy for an app-owned flow', () => {
  beforeEach(() => {
    vi.resetModules();
    panels.length = 0;
    postMessage.mockClear();
    get.mockReset().mockImplementation((method: string) =>
      Promise.resolve({ message: method.endsWith('get_pending_approvals') ? [] : { version: 3 } }),
    );
    post.mockReset().mockResolvedValue({ message: [] });
    window.history.replaceState({}, '', '/huf/embed/flow/f1?app=happiol');
    Object.defineProperty(window, 'parent', { configurable: true, value: { postMessage } });
    setBoot(POLICY);
  });
  afterEach(() => {
    cleanup();
    Object.defineProperty(window, 'parent', { configurable: true, value: originalParent });
  });

  it('opens for an app-only user and shows Save, a dry-run Test, Runs, approvals and People, but no publish or settings', async () => {
    await open();
    expect(screen.getByTestId('embed-toolbar')).toBeTruthy();
    expect(screen.getByTestId('flow-save')).toBeTruthy();
    expect(screen.getByTestId('flow-run').textContent).toContain('Test (no messages sent)');
    expect(screen.getByTestId('embed-approvals-open')).toBeTruthy();
    for (const id of ['flow-publish', 'flow-unpublish', 'flow-settings']) expect(screen.queryByTestId(id)).toBeNull();
    expect(screen.queryByText(/publish|settings/i)).toBeNull();
    // can_write follows the policy, not a Huf role.
    expect(postMessage.mock.calls.find(([m]) => m.type === 'guest.loaded')?.[0].payload.can_write).toBe(true);
  });

  it('has no keyboard or palette path to publish or settings', async () => {
    await open();
    const { runFlowCommand } = await import('@/components/flow/shortcuts/flowCommands');
    expect(runFlowCommand('publish')).toBe(false);
    expect(runFlowCommand('settings')).toBe(false);
  });

  it('is read-only without can_edit and hides approvals without can_approve', async () => {
    setBoot({ ...POLICY, can_edit: false, can_approve: false });
    await open();
    expect(screen.getByTestId('embed-view-only')).toBeTruthy();
    expect(screen.queryByTestId('flow-save')).toBeNull();
    expect(screen.queryByTestId('embed-approvals-open')).toBeNull();
    expect(postMessage.mock.calls.find(([m]) => m.type === 'guest.loaded')?.[0].payload.can_write).toBe(false);
  });

  it('scopes every drawer to this flow', async () => {
    await open();
    fireEvent.click(screen.getByTestId('flow-runs'));
    fireEvent.click(screen.getByTestId('flow-members-open'));
    get.mockClear();
    fireEvent.click(screen.getByTestId('embed-approvals-open'));
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(panels).toContainEqual(['runs', 'f1']);
    expect(panels).toContainEqual(['people', 'f1']);
    expect(get.mock.calls).toEqual([['huf.ai.flow.api.get_pending_approvals', { flow_id: 'f1' }]]);
  });

  it('sends seeded /huf and desk links to the host instead of following them', async () => {
    const router = await open();
    postMessage.mockClear();
    for (const text of ['Huf flows', 'Run form', 'Flow form', 'Approvals', 'Agent']) {
      await act(async () => screen.getByText(text).click());
    }
    expect(router.state.location.pathname).toBe('/huf/embed/flow/f1');
    expect(window.location.pathname).toBe('/huf/embed/flow/f1');
    expect(navigations()).toEqual([
      { target: 'flow_list' },
      { target: 'run', run_id: 'RUN-1' },
      { target: 'flow_list' },
      { target: 'approvals' },
    ]);
  });

  it('never puts flow names or other content in a message (G4)', async () => {
    await open();
    await act(async () => screen.getByText('Agent').click());
    fireEvent.click(screen.getByTestId('embed-approvals-open'));
    expect(JSON.stringify(postMessage.mock.calls)).not.toContain(SENTINEL);
    expect(JSON.stringify(postMessage.mock.calls)).not.toContain('9999000000');
  });

  it('refuses an app-only user on a Huf-native flow (no policy)', async () => {
    setBoot(undefined);
    // Without a policy an app-only user (no flows.use) is refused.
    await open();
    expect(screen.getByTestId('embed-not-permitted')).toBeTruthy();
  });
});

describe('approval drawer', () => {
  beforeEach(() => {
    vi.resetModules();
    get.mockReset().mockResolvedValue({
      message: [
        { flow_run_id: 'R1', flow_id: 'f1', title: 'Check', instructions: '', view_link: '/huf/flows/f1?run=R1' },
        { flow_run_id: 'R9', flow_id: 'other', title: 'Other flow', instructions: '', view_link: '/huf/flows/other' },
      ],
    });
    post.mockReset().mockResolvedValue({ message: {} });
  });
  afterEach(cleanup);

  it('lists only this flow, renders no server link, and needs a reason to reject', async () => {
    const { EmbedApprovalsDrawer } = await import('./EmbedApprovalsDrawer');
    render(<EmbedApprovalsDrawer flowId="f1" open onOpenChange={() => undefined} onOpenRun={() => undefined} />);
    await waitFor(() => expect(screen.getAllByTestId('embed-approval-row')).toHaveLength(1));
    expect(document.body.innerHTML).not.toContain('/huf/');
    const reject = screen.getByTestId('embed-reject') as HTMLButtonElement;
    expect(reject.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Wrong offer' } });
    await act(async () => reject.click());
    expect(post).toHaveBeenCalledWith('huf.ai.flow.api.reject_flow_run', { flow_run_id: 'R1', comment: 'Wrong offer' });
  });
});

describe('navigate message validation (mount)', () => {
  it('accepts run with an id and approvals, and refuses ids anywhere else', async () => {
    const { parseGuestMessage } = await import('./mount');
    const msg = (payload: object) => ({ ns: 'huf.flow.embed', v: 1, type: 'guest.navigate', payload });
    expect(parseGuestMessage(msg({ target: 'run', run_id: 'R1' }))).toEqual({ event: 'navigate', detail: { target: 'run', run_id: 'R1' } });
    expect(parseGuestMessage(msg({ target: 'approvals' }))).toEqual({ event: 'navigate', detail: { target: 'approvals' } });
    expect(parseGuestMessage(msg({ target: 'run' }))).toBeNull();
    expect(parseGuestMessage(msg({ target: 'providers', run_id: 'R1' }))).toBeNull();
    expect(parseGuestMessage(msg({ target: 'run', run_id: 5 }))).toBeNull();
  });
});
