import { Component, useCallback, useContext, useEffect, useMemo, useRef, useSyncExternalStore, type ReactNode } from 'react';
import { useBlocker, useLocation, useNavigate, useParams, type Location } from 'react-router-dom';
import { AuthenticatingPage } from '@/components/AuthenticatingPage';
import { FlowsHeaderActions } from '@/components/FlowsHeaderActions';
import { embedApp } from '@/components/flow/palette/embedScope';
import { ShortcutsHelpProvider } from '@/components/shortcuts/ShortcutsHelpContext';
import { Button } from '@/components/ui/button';
import { TooltipProvider } from '@/components/ui/tooltip';
import { FlowProvider, useFlowContext } from '@/contexts/FlowContext';
import { ModalProvider } from '@/contexts/ModalContext';
import { PermissionsContext, usePermissions } from '@/contexts/PermissionsContext';
import { useUser } from '@/contexts/UserContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { isEmbedSessionExpired, subscribeEmbedSession } from '@/lib/sessionInvalidation';
import { FlowCanvasPage } from '@/pages/FlowCanvasPage';
import { embedBoot, embedPolicy, postToHost, type EmbedPolicy, type ErrorCode } from './bridge';
import { classifyEmbedHref, classifyEmbedNavigation, type EmbedNavigation } from './navigation';
import { EmbedToolbar } from './EmbedToolbar';
import { useEmbedLoad } from './useEmbedLoad';

const FAILURES = {
  not_found: { testId: 'embed-not-found', message: 'This flow was not found.' },
  not_permitted: { testId: 'embed-not-permitted', message: "You don't have access to this page." },
  unknown_app: { testId: 'embed-unknown-app', message: 'This editor is not set up correctly.' },
  load_failed: { testId: 'embed-load-failed', message: 'The flow editor could not be loaded.' },
};

interface EmbedStateProps {
  testId: string;
  message: string;
  /** Told to the host once, when given. */
  code?: ErrorCode;
  flowId?: string;
  children?: ReactNode;
}

function EmbedState({ testId, message, code, flowId, children }: EmbedStateProps) {
  useEffect(() => {
    if (code) postToHost('guest.error', flowId ? { code, flow_id: flowId } : { code });
  }, [code, flowId]);

  return (
    <div className="flex h-svh w-full flex-col items-center justify-center gap-3 p-6 text-center" role="alert" data-testid={testId}>
      <p className="font-body text-ink">{message}</p>
      {children}
    </div>
  );
}

/** Keeps a crash inside the embed: the app-wide boundary offers a way out to /huf. */
class EmbedErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <EmbedState testId="embed-load-failed" code="load_failed" message="The flow editor could not be loaded.">
        <Button size="sm" onClick={() => window.location.reload()}>Retry</Button>
      </EmbedState>
    );
  }
}

/** Acts on a navigation decision: rewrite inside the frame, or tell the host. */
function useFollow() {
  const navigate = useNavigate();
  return useCallback(
    (decision: EmbedNavigation) => {
      if (decision.kind === 'rewrite') navigate(decision.to);
      else if (decision.kind === 'leave' && decision.target) postToHost('guest.navigate', decision.target);
    },
    [navigate],
  );
}

/** No in-app navigation leaves the editor; links that would are reported to the host. */
function useStayInEditor() {
  const location = useLocation();
  const follow = useFollow();
  const blocker = useBlocker(
    useCallback(
      ({ currentLocation, nextLocation }: { currentLocation: Location; nextLocation: Location }) =>
        classifyEmbedNavigation(currentLocation, nextLocation).kind !== 'stay',
      [],
    ),
  );

  useEffect(() => {
    if (blocker.state !== 'blocked') return;
    const decision = classifyEmbedNavigation(location, blocker.location);
    blocker.reset();
    follow(decision);
  }, [blocker, location, follow]);

  // Plain links (a rendered `<a href="/huf/...">` or `/app/...`) never replace the frame either.
  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const anchor = (event.target as Element | null)?.closest?.('a[href]');
      if (!anchor || event.defaultPrevented) return;
      const decision = classifyEmbedHref(anchor.getAttribute('href') ?? '', window.location);
      if (!decision || decision.kind === 'stay') return;
      event.preventDefault();
      if (decision.kind === 'rewrite') follow({ kind: 'rewrite', to: decision.to.replace(/^\/huf(?=\/)/, '') });
      else follow(decision);
    };
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, [follow]);
}

/**
 * For an app-owned flow the server's policy, not a Huf role, says what the user may do (H-W7-09). The editor's own
 * checks read capabilities, so they are derived from the policy here. The server checks every call again.
 */
function PolicyPermissions({ policy, children }: { policy: EmbedPolicy; children: ReactNode }) {
  const parent = useContext(PermissionsContext);
  const value = useMemo(() => {
    const granted = new Set(['flows.use', ...(policy.can_edit ? ['flows.manage'] : [])]);
    return {
      hufRole: parent?.hufRole ?? null,
      capabilities: [...granted],
      withheldCapabilities: [],
      docPermissions: parent?.docPermissions,
      isLoading: false,
      hasCapability: (capability: string) => granted.has(capability),
      refresh: parent?.refresh ?? (async () => undefined),
    };
  }, [policy.can_edit, parent]);
  return <PermissionsContext.Provider value={value}>{children}</PermissionsContext.Provider>;
}

/** Tells the host that the flow is on screen, then about each change of its unsaved state. */
function useReportFlow(version: number) {
  const { activeFlow, hasUnsavedChanges } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const flowId = activeFlow?.id;
  const status = activeFlow?.status === 'active' ? 'Active' : 'Draft';
  const loaded = useRef(false);
  const dirty = useRef(false);

  useEffect(() => {
    if (!flowId || loaded.current) return;
    loaded.current = true;
    postToHost('guest.loaded', { flow_id: flowId, version, status, can_write: canManage });
  }, [flowId, version, status, canManage]);

  useEffect(() => {
    if (!flowId || dirty.current === hasUnsavedChanges) return;
    dirty.current = hasUnsavedChanges;
    postToHost('guest.dirty', { flow_id: flowId, dirty: hasUnsavedChanges });
  }, [flowId, hasUnsavedChanges]);
}

function EmbedEditor({ version, policy }: { version: number; policy: EmbedPolicy | null }) {
  const { activeFlow } = useFlowContext();
  useStayInEditor();
  useReportFlow(version);

  return (
    <div className="flex h-svh max-h-svh flex-col overflow-hidden" data-testid="embed-flow-editor">
      <header className="flex min-h-[46px] shrink-0 flex-wrap items-center gap-2 border-b border-line bg-panel px-4">
        <span className="min-w-0 flex-1 truncate text-ui-text font-medium text-ink" data-testid="flow-name">
          {activeFlow?.name}
        </span>
        {policy ? <EmbedToolbar policy={policy} /> : <FlowsHeaderActions />}
      </header>
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <FlowCanvasPage />
      </main>
    </div>
  );
}

/** Loads the palette scope and the flow before the editor, so a failure is shown instead of an empty editor. */
function EmbedFlow({ flowId, policy }: { flowId: string; policy: EmbedPolicy | null }) {
  const { result, retry } = useEmbedLoad(flowId, embedApp());

  if (result.state === 'loading') return <AuthenticatingPage />;
  if (result.state === 'failed') {
    const { testId, message } = FAILURES[result.code];
    return (
      <EmbedState testId={testId} message={message} code={result.code} flowId={flowId}>
        {result.code === 'load_failed' && <Button size="sm" onClick={retry}>Retry</Button>}
      </EmbedState>
    );
  }

  const editor = (
    <EmbedErrorBoundary>
      <TooltipProvider>
        <ShortcutsHelpProvider>
          <FlowProvider>
            <ModalProvider>
              <EmbedEditor version={result.version} policy={policy} />
            </ModalProvider>
          </FlowProvider>
        </ShortcutsHelpProvider>
      </TooltipProvider>
    </EmbedErrorBoundary>
  );
  return policy ? <PolicyPermissions policy={policy}>{editor}</PolicyPermissions> : editor;
}

export default function EmbedFlowPage() {
  const { flowId } = useParams<{ flowId: string }>();
  const expired = useSyncExternalStore(subscribeEmbedSession, isEmbedSessionExpired);
  const { isLoading, isAuthenticated } = useUser();
  const { isLoading: permissionsLoading, hasCapability } = usePermissions();

  // `session_expired` was already sent by whoever noticed the lost session.
  if (expired) return <EmbedState testId="embed-signed-out" message="You are signed out." />;
  if (isLoading || permissionsLoading) return <AuthenticatingPage />;
  if (!isAuthenticated) return <EmbedState testId="embed-signed-out" code="session_expired" message="You are signed out." />;
  if (!flowId) return <EmbedState {...FAILURES.not_found} code="not_found" />;
  // Without the server's embed boot data its frame and access checks did not run.
  // An app-owned flow carries the server's policy: its access check already ran, without a Huf role.
  const policy = embedPolicy();
  if (!embedBoot() || (!policy && !hasCapability('flows.use'))) {
    return <EmbedState {...FAILURES.not_permitted} code="not_permitted" />;
  }

  return <EmbedFlow key={flowId} flowId={flowId} policy={policy} />;
}
