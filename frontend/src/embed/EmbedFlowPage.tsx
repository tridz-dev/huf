import { Component, useCallback, useEffect, useSyncExternalStore, type ReactNode } from 'react';
import { useBlocker, useLocation, useNavigate, useParams, type Location } from 'react-router-dom';
import { AuthenticatingPage } from '@/components/AuthenticatingPage';
import { FlowsHeaderActions } from '@/components/FlowsHeaderActions';
import { ShortcutsHelpProvider } from '@/components/shortcuts/ShortcutsHelpContext';
import { Button } from '@/components/ui/button';
import { TooltipProvider } from '@/components/ui/tooltip';
import { FlowProvider, useFlowContext } from '@/contexts/FlowContext';
import { ModalProvider } from '@/contexts/ModalContext';
import { usePermissions } from '@/contexts/PermissionsContext';
import { useUser } from '@/contexts/UserContext';
import { isEmbedSessionExpired, subscribeEmbedSession } from '@/lib/sessionInvalidation';
import { FlowCanvasPage } from '@/pages/FlowCanvasPage';
import { embedBoot, postToHost } from './bridge';
import { classifyEmbedNavigation } from './navigation';

function EmbedState({ testId, message, children }: { testId: string; message: string; children?: ReactNode }) {
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
      <EmbedState testId="embed-load-failed" message="The flow editor could not be loaded.">
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

function EmbedEditor() {
  const { activeFlow } = useFlowContext();
  useStayInEditor();

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

export default function EmbedFlowPage() {
  const { flowId } = useParams<{ flowId: string }>();
  const expired = useSyncExternalStore(subscribeEmbedSession, isEmbedSessionExpired);
  const { isLoading, isAuthenticated } = useUser();
  const { isLoading: permissionsLoading, hasCapability } = usePermissions();

  if (expired) return <EmbedState testId="embed-signed-out" message="You are signed out." />;
  if (isLoading || permissionsLoading) return <AuthenticatingPage />;
  if (!isAuthenticated) return <EmbedState testId="embed-signed-out" message="You are signed out." />;
  if (!flowId) return <EmbedState testId="embed-not-found" message="This flow was not found." />;
  // Without the server's embed boot data its frame and access checks did not run.
  if (!embedBoot() || !hasCapability('flows.use')) {
    return <EmbedState testId="embed-not-permitted" message="You don't have access to this page." />;
  }

  return (
    <EmbedErrorBoundary>
      <TooltipProvider>
        <ShortcutsHelpProvider>
          <FlowProvider>
            <ModalProvider>
              <EmbedEditor />
            </ModalProvider>
          </FlowProvider>
        </ShortcutsHelpProvider>
      </TooltipProvider>
    </EmbedErrorBoundary>
  );
}
