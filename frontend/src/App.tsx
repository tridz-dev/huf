import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { UserProvider } from './contexts/UserContext';
import { PermissionsProvider, usePermissions } from './contexts/PermissionsContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AuthenticatingPage } from './components/AuthenticatingPage';
import { FlowProvider } from './contexts/FlowContext';
import { ModalProvider } from './contexts/ModalContext';
import { UnifiedLayout } from './layouts/UnifiedLayout';
import { HomeHeaderActions } from './components/HomeHeaderActions';
import { AgentsHeaderActions } from './components/AgentsHeaderActions';
import { McpHeaderActions } from './components/McpHeaderActions';
import { FlowsListHeaderActions } from './components/FlowsListHeaderActions';
import { KnowledgeHeaderActions } from './components/KnowledgeHeaderActions';
import { SkillsHeaderActions } from './components/skills/SkillsHeaderActions';
import { AgentPromptsHeaderActions } from './components/AgentPromptsHeaderActions';
import { AgentSummaryPromptsHeaderActions } from './components/AgentSummaryPromptsHeaderActions';
import { ExecutionProfilesHeaderActions } from './components/ExecutionProfilesHeaderActions';
import { SSHConnectionsHeaderActions } from './components/SSHConnectionsHeaderActions';
import { UsersHeaderActions } from './components/UsersHeaderActions';
import { PageLoader } from './components/PageLoader';
import { DataHeaderActions } from './components/DataHeaderActions';
import { DataTableBuilderWrapper } from './pages/DataTableBuilderWrapper';
import { DataTableViewWrapper } from './pages/DataTableViewWrapper';
import { Toaster } from './components/ui/sonner';

const HomePage = lazy(() => import('./pages/HomePage'));
const AppsPage = lazy(() => import('./pages/AppsPage'));
const AgentsPage = lazy(() => import('./pages/AgentsPage'));
const AgentFormPageWrapper = lazy(() => import('./pages/AgentFormPageWrapper'));
const AgentPromptsPage = lazy(() => import('./pages/AgentPromptsPage'));
const AgentPromptFormPageWrapper = lazy(() => import('./pages/AgentPromptFormPageWrapper'));
const AgentSummaryPromptsPage = lazy(() => import('./pages/AgentSummaryPromptsPage'));
const AgentSummaryPromptFormPageWrapper = lazy(() => import('./pages/AgentSummaryPromptFormPageWrapper'));
const ExecutionProfilesPage = lazy(() => import('./pages/ExecutionProfilesPage'));
const ExecutionProfileFormPageWrapper = lazy(() => import('./pages/ExecutionProfileFormPageWrapper'));
const SSHConnectionsPage = lazy(() => import('./pages/SSHConnectionsPage'));
const SSHConnectionFormPageWrapper = lazy(() => import('./pages/SSHConnectionFormPageWrapper'));
const FlowListPage = lazy(() => import('./pages/FlowListPage'));
const FlowCanvasPageWrapper = lazy(() => import('./pages/FlowCanvasPageWrapper'));
const DataPage = lazy(() => import('./pages/DataPage'));
const AiProvidersPageWrapper = lazy(() => import('./pages/AiProvidersPageWrapper'));
const ChatPage = lazy(() => import('./pages/ChatPageV2'));
const ChatOnlyPage = lazy(() => import('./pages/ChatOnlyPage'));
const Executions = lazy(() => import('./pages/Executions'));
const AgentRunDetailPageWrapper = lazy(() => import('./pages/AgentRunDetailPageWrapper'));
const AgentContextArtifactsPage = lazy(() => import('./pages/AgentContextArtifactsPage'));
const AgentContextArtifactDetailPage = lazy(() => import('./pages/AgentContextArtifactDetailPage'));
const McpDetailsPageWrapper = lazy(() => import('./pages/McpDetailsPageWrapper'));
const McpListingPage = lazy(() => import('./pages/McpListingPage'));
const KnowledgeSourcesPage = lazy(() => import('./pages/KnowledgeSourcesPage'));
const KnowledgeSourceFormPageWrapper = lazy(() => import('./pages/KnowledgeSourceFormPageWrapper'));
const MemoryPage = lazy(() => import('./pages/MemoryPage'));
const SkillsPage = lazy(() => import('./pages/SkillsPage'));
const SkillFormPageWrapper = lazy(() => import('./pages/SkillFormPageWrapper'));
const SshPage = lazy(() => import('./pages/SshPage'));
const PreviewViewPage = lazy(() => import('./pages/PreviewViewPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));
const DataRecordViewWrapper = lazy(() => import('./pages/DataRecordViewWrapper'));
const ModelsPageWrapper = lazy(() => import('./pages/ModelsPageWrapper'));
const ConsolePage = lazy(() => import('./pages/ConsolePage'));
const IntegrationSettingsListingPageWrapper = lazy(
  () => import('./pages/IntegrationSettingsListingPageWrapper'),
);
const IntegrationSettingsDetailsPageWrapper = lazy(
  () => import('./pages/IntegrationSettingsDetailsPageWrapper'),
);
const IntegrationServicesListingPageWrapper = lazy(
  () => import('./pages/IntegrationServicesListingPageWrapper'),
);
const IntegrationServiceFormPageWrapper = lazy(
  () => import('./pages/IntegrationServiceFormPageWrapper'),
);
const HubSimplePage = lazy(() => import('./pages/HubSimplePage'));
// TODO(#473-followup): Gateways page is kept in source but unlinked from routes
// while the feature is incomplete. See docs/gateway-todo.md.
// const GatewaysPage = lazy(() => import('./pages/GatewaysPage'));
const AgentSettingsPage = lazy(() => import('./pages/AgentSettingsPage'));

import { useEffect } from 'react';
import { RouteErrorBoundary, clearChunkReloadFlag } from './components/RouteErrorBoundary';
import { SocketProvider } from './contexts/SocketContext';
import {
  checkStreamingAvailable,
  setStreamingAvailable,
} from './services/streamChatApi';
const UsersPage = lazy(() => import('./pages/UsersPage'));
const RolesPage = lazy(() => import('./pages/RolesPage'));

function ChatOnlyRedirectGuard() {
  const location = useLocation();
  const { capabilities, isLoading } = usePermissions();
  // Chat-only users get `chat.use` plus nothing outside the chat.* namespace
  // (e.g. `chat.view_own` is fine, but `agent.use` means they are a full user).
  const isChatOnlyUser =
    capabilities.includes('chat.use') &&
    capabilities.every((capability) => capability.startsWith('chat.'));
  const isAllowedChatOnlyPath =
    location.pathname.startsWith('/ui/chat') || location.pathname.startsWith('/view/');

  if (isLoading || !isChatOnlyUser || isAllowedChatOnlyPath) {
    return null;
  }

  return <Navigate to="/ui/chat" replace />;
}

function AppShell() {
  const location = useLocation();

  useEffect(() => {
    clearChunkReloadFlag();
  }, []);

  return (
    <SocketProvider>
      <UserProvider>
        <PermissionsProvider>
          <ChatOnlyRedirectGuard />
          <Suspense fallback={<AuthenticatingPage />}>
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={location.pathname}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="h-full"
              >
                <Routes location={location}>
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <HubSimplePage />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<HomeHeaderActions />}>
                  <Suspense fallback={<PageLoader />}>
                    <HomePage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/apps"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <AppsPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/agents"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<AgentsHeaderActions />}>
                  <Suspense fallback={<PageLoader />}>
                    <AgentsPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/agents/:id"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <AgentFormPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/prompts"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<AgentPromptsHeaderActions />}>
                  <Suspense fallback={<PageLoader />}>
                    <AgentPromptsPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/prompts/:id"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <AgentPromptFormPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/summary-prompts"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<AgentSummaryPromptsHeaderActions />}>
                  <Suspense fallback={<PageLoader />}>
                    <AgentSummaryPromptsPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/summary-prompts/:id"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <AgentSummaryPromptFormPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/execution-profiles"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<ExecutionProfilesHeaderActions />}>
                  <Suspense fallback={<PageLoader />}>
                    <ExecutionProfilesPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/execution-profiles/:id"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <ExecutionProfileFormPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ssh-connections"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<SSHConnectionsHeaderActions />}>
                  <Suspense fallback={<PageLoader />}>
                    <SSHConnectionsPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ssh-connections/:id"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <SSHConnectionFormPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/data"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<DataHeaderActions />}>
                  <Suspense fallback={<PageLoader />}>
                    <DataPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/console"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <ConsolePage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/data/new"
            element={
              <ProtectedRoute requiredCapability="data.tables.manage">
                <DataTableBuilderWrapper />
              </ProtectedRoute>
            }
          />
          <Route
            path="/data/:tableId"
            element={
              <ProtectedRoute>
                <DataTableViewWrapper />
              </ProtectedRoute>
            }
          />
          <Route
            path="/data/:tableId/:recordName"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <DataRecordViewWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/data/:tableId/edit"
            element={
              <ProtectedRoute requiredCapability="data.tables.manage">
                <DataTableBuilderWrapper />
              </ProtectedRoute>
            }
          />
          <Route
            path="/models"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <ModelsPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/providers"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <AiProvidersPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/flows"
            element={
              <ProtectedRoute>
                <FlowProvider>
                  <UnifiedLayout headerActions={<FlowsListHeaderActions />}>
                    <Suspense fallback={<PageLoader />}>
                      <FlowListPage />
                    </Suspense>
                  </UnifiedLayout>
                </FlowProvider>
              </ProtectedRoute>
            }
          />
          <Route
            path="/flows/:flowId"
            element={
              <ProtectedRoute>
                <FlowProvider>
                  <ModalProvider>
                    <Suspense fallback={<PageLoader />}>
                      <FlowCanvasPageWrapper />
                    </Suspense>
                  </ModalProvider>
                </FlowProvider>
              </ProtectedRoute>
            }
          />
          <Route
            path="/chat"
            element={
              <ProtectedRoute>
                <UnifiedLayout hideHeader>
                  <Suspense fallback={<PageLoader />}>
                    <ChatPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/chat/:chatId"
            element={
              <ProtectedRoute>
                <UnifiedLayout hideHeader>
                  <Suspense fallback={<PageLoader />}>
                    <ChatPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ui/chat"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <ChatOnlyPage />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ui/chat/:chatId"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <ChatOnlyPage />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/executions"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <Executions />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/executions/:runId"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <AgentRunDetailPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/artifacts"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <AgentContextArtifactsPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/artifacts/:artifactId"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <AgentContextArtifactDetailPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <AgentSettingsPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/knowledge"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<KnowledgeHeaderActions />}>
                  <Suspense fallback={<PageLoader />}>
                    <KnowledgeSourcesPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/memory"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <MemoryPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/knowledge/:id"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <KnowledgeSourceFormPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/skills"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<SkillsHeaderActions />}>
                  <Suspense fallback={<PageLoader />}>
                    <SkillsPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/skills/:id"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <SkillFormPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ssh"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <SshPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/integrations"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <IntegrationSettingsListingPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/integrations/:settingId"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <IntegrationSettingsDetailsPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          {/* TODO(#473-followup): Gateways route is disabled while the feature is
              incomplete. Restore once docs/gateway-todo.md items are resolved. */}
          {/* <Route
            path="/gateways"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <GatewaysPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          /> */}
          <Route
            path="/integration-services"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <IntegrationServicesListingPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/integration-services/:serviceId"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <IntegrationServiceFormPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/mcp"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<McpHeaderActions />}>
                  <Suspense fallback={<PageLoader />}>
                    <McpListingPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/mcp/:mcpId"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <McpDetailsPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/view/:messageId"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <PreviewViewPage />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/users"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<UsersHeaderActions />}>
                  <UsersPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/roles"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <RolesPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="*"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <NotFoundPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
                </Routes>
              </motion.div>
            </AnimatePresence>
          </Suspense>
          <Toaster />
        </PermissionsProvider>
      </UserProvider>
    </SocketProvider>
  );
}

const router = createBrowserRouter(
  [{ path: '*', element: <AppShell />, errorElement: <RouteErrorBoundary /> }],
  { basename: '/huf' },
);

function App() {
  useEffect(() => {
    // Streaming (SSE) is the explicit direct-execution mode: it is only used
    // for agents with the advanced `run_immediately` policy enabled. Ordinary
    // chat turns go through the queue-first REST path regardless of this
    // probe, so a failed probe is informational, not an error.
    checkStreamingAvailable().then((ok) => {
      console.log("Streaming available:", ok);
      setStreamingAvailable(ok);
    });
  }, []);

  return <RouterProvider router={router} />;
}

export default App;
