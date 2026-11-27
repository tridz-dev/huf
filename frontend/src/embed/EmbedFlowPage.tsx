import { Component, useCallback, useEffect, useRef, useSyncExternalStore, type ReactNode } from 'react';
import { useBlocker, useLocation, useNavigate, useParams, type Location } from 'react-router-dom';
import { AuthenticatingPage } from '@/components/AuthenticatingPage';
import { FlowsHeaderActions } from '@/components/FlowsHeaderActions';
import { embedApp } from '@/components/flow/palette/embedScope';
import { ShortcutsHelpProvider } from '@/components/shortcuts/ShortcutsHelpContext';
import { Button } from '@/components/ui/button';
import { TooltipProvider } from '@/components/ui/tooltip';
import { FlowProvider, useFlowContext } from '@/contexts/FlowContext';
import { ModalProvider } from '@/contexts/ModalContext';
import { usePermissions } from '@/contexts/PermissionsContext';
import { useUser } from '@/contexts/UserContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { isEmbedSessionExpired, subscribeEmbedSession } from '@/lib/sessionInvalidation';
import { FlowCanvasPage } from '@/pages/FlowCanvasPage';
import { embedBoot, postToHost, type ErrorCode } from './bridge';
import { classifyEmbedNavigation } from './navigation';
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

/** No in-app navigation leaves the editor; links that would are reported to the host. */
function useStayInEditor() {
  const navigate = useNavigate();
  const location = useLocation();
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
    if (decision.kind === 'rewrite') navigate(decision.to);
    else if (decision.kind === 'leave' && decision.target) postToHost('guest.navigate', { target: decision.target });
  }, [blocker, location, navigate]);
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

function EmbedEditor({ version }: { version: number }) {
  const { activeFlow } = useFlowContext();
  useStayInEditor();
  useReportFlow(version);

  return (
    <div className="flex h-svh max-h-svh flex-col overflow-hidden" data-testid="embed-flow-editor">
      <header className="flex min-h-[46px] shrink-0 flex-wrap items-center gap-2 border-b border-line bg-panel px-4">
        <span className="min-w-0 flex-1 truncate text-ui-text font-medium text-ink" data-testid="flow-name">
          {activeFlow?.name}
        </span>
        <FlowsHeaderActions />
      </header>
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <FlowCanvasPage />
      </main>
    </div>
  );
}

/** Loads the palette scope and the flow before the editor, so a failure is shown instead of an empty editor. */
function EmbedFlow({ flowId }: { flowId: string }) {
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

  return (
    <EmbedErrorBoundary>
      <TooltipProvider>
        <ShortcutsHelpProvider>
          <FlowProvider>
            <ModalProvider>
              <EmbedEditor version={result.version} />
            </ModalProvider>
          </FlowProvider>
        </ShortcutsHelpProvider>
      </TooltipProvider>
    </EmbedErrorBoundary>
  );
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
  if (!embedBoot() || !hasCapability('flows.use')) {
    return <EmbedState {...FAILURES.not_permitted} code="not_permitted" />;
  }

  return <EmbedFlow key={flowId} flowId={flowId} />;
}
