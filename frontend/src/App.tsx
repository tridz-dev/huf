import { lazy, Suspense, useEffect } from 'react';
import { createBrowserRouter, RouterProvider, Routes, Route, Navigate, useLocation, Outlet } from 'react-router-dom';
import { UserProvider } from './contexts/UserContext';
import { PermissionsProvider, usePermissions } from './contexts/PermissionsContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AuthenticatingPage } from './components/AuthenticatingPage';
import { FlowProvider } from './contexts/FlowContext';
import { ModalProvider } from './contexts/ModalContext';
import { AppShellLayout } from './layouts/AppShellLayout';
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
import { RouteErrorBoundary, clearChunkReloadFlag } from './components/RouteErrorBoundary';
import { initTheme } from './lib/personalization';
import { SocketProvider } from './contexts/SocketContext';
import {
  checkStreamingAvailable,
  setStreamingAvailable,
} from './services/streamChatApi';

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
const McpDetailsPageWrapper = lazy(() => import('./pages/McpDetailsPageWrapper'));
const McpListingPage = lazy(() => import('./pages/McpListingPage'));
const KnowledgeSourcesPage = lazy(() => import('./pages/KnowledgeSourcesPage'));
const KnowledgeSourceFormPageWrapper = lazy(() => import('./pages/KnowledgeSourceFormPageWrapper'));
const MemoryPage = lazy(() => import('./pages/MemoryPage'));
const MemoryPolicyFormPageWrapper = lazy(() => import('./pages/MemoryPolicyFormPageWrapper'));
const SkillsPage = lazy(() => import('./pages/SkillsPage'));
const SkillFormPageWrapper = lazy(() => import('./pages/SkillFormPageWrapper'));
const SshPage = lazy(() => import('./pages/SshPage'));
const PreviewViewPage = lazy(() => import('./pages/PreviewViewPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));
const DataRecordViewWrapper = lazy(() => import('./pages/DataRecordViewWrapper'));
const ModelsPageWrapper = lazy(() => import('./pages/ModelsPageWrapper'));
const PlaygroundPage = lazy(() => import('./pages/PlaygroundPage'));
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
const GatewaysPage = lazy(() => import('./pages/GatewaysPage'));
const AgentSettingsPage = lazy(() => import('./pages/AgentSettingsPage'));
const GeneralSettingsPage = lazy(() => import('./pages/GeneralSettingsPage'));
const UsersPage = lazy(() => import('./pages/UsersPage'));
const RolesPage = lazy(() => import('./pages/RolesPage'));
const MembersPage = lazy(() => import('./pages/MembersPage'));

function ChatOnlyRedirectGuard() {
  const location = useLocation();
  const { capabilities, isLoading } = usePermissions();
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

function FlowRoutes() {
  return (
    <FlowProvider>
      <Outlet />
    </FlowProvider>
  );
}

function AppShell() {
  useEffect(() => {
    clearChunkReloadFlag();
  }, []);

  useEffect(() => {
    initTheme();
  }, []);

  return (
    <SocketProvider>
      <UserProvider>
        <PermissionsProvider>
          <ChatOnlyRedirectGuard />
          <Suspense fallback={<AuthenticatingPage />}>
            <Routes>
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
                element={
                  <ProtectedRoute>
                    <AppShellLayout />
                  </ProtectedRoute>
                }
              >
                <Route
                  path="/"
                  handle={{ hideHeader: true }}
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <HubSimplePage />
                    </Suspense>
                  }
                />
                <Route
                  path="/dashboard"
                  handle={{ headerActions: <HomeHeaderActions /> }}
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <HomePage />
                    </Suspense>
                  }
                />
                <Route
                  path="/apps"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <AppsPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/agents"
                  handle={{ headerActions: <AgentsHeaderActions /> }}
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <AgentsPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/agents/:id"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <AgentFormPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/prompts"
                  handle={{ headerActions: <AgentPromptsHeaderActions /> }}
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <AgentPromptsPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/prompts/:id"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <AgentPromptFormPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/summary-prompts"
                  handle={{ headerActions: <AgentSummaryPromptsHeaderActions /> }}
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <AgentSummaryPromptsPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/summary-prompts/:id"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <AgentSummaryPromptFormPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/execution-profiles"
                  handle={{ headerActions: <ExecutionProfilesHeaderActions /> }}
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <ExecutionProfilesPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/execution-profiles/:id"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <ExecutionProfileFormPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/ssh-connections"
                  handle={{ headerActions: <SSHConnectionsHeaderActions /> }}
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <SSHConnectionsPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/ssh-connections/:id"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <SSHConnectionFormPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/data"
                  handle={{ headerActions: <DataHeaderActions /> }}
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <DataPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/playground"
                  handle={{ hideHeader: true }}
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <PlaygroundPage />
                    </Suspense>
                  }
                />
                <Route path="/console" element={<Navigate to="/playground" replace />} />
                <Route
                  path="/data/new"
                  element={
                    <ProtectedRoute requiredCapability="data.tables.manage">
                      <DataTableBuilderWrapper />
                    </ProtectedRoute>
                  }
                />
                <Route path="/data/:tableId" element={<DataTableViewWrapper />} />
                <Route
                  path="/data/:tableId/:recordName"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <DataRecordViewWrapper />
                    </Suspense>
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
                    <Suspense fallback={<PageLoader />}>
                      <ModelsPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/providers"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <AiProvidersPageWrapper />
                    </Suspense>
                  }
                />
                <Route element={<FlowRoutes />}>
                  <Route
                    path="/flows"
                    handle={{ headerActions: <FlowsListHeaderActions /> }}
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <FlowListPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/flows/:flowId"
                    element={
                      <ModalProvider>
                        <Suspense fallback={<PageLoader />}>
                          <FlowCanvasPageWrapper />
                        </Suspense>
                      </ModalProvider>
                    }
                  />
                </Route>
                <Route
                  path="/chat/:chatId?"
                  handle={{ hideHeader: true }}
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <ChatPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/executions"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <Executions />
                    </Suspense>
                  }
                />
                <Route
                  path="/executions/:runId"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <AgentRunDetailPageWrapper />
                    </Suspense>
                  }
                />
                <Route path="/artifacts/*" element={<Navigate to="/executions" replace />} />
                <Route path="/channels/*" element={<Navigate to="/gateways" replace />} />
                <Route
                  path="/settings"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <AgentSettingsPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/settings/general"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <GeneralSettingsPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/knowledge"
                  handle={{ headerActions: <KnowledgeHeaderActions /> }}
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <KnowledgeSourcesPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/memory"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <MemoryPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/knowledge/:id"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <KnowledgeSourceFormPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/memory/policies/:id"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <MemoryPolicyFormPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/skills"
                  handle={{ headerActions: <SkillsHeaderActions /> }}
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <SkillsPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/skills/:id"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <SkillFormPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/ssh"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <SshPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/integrations"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <IntegrationSettingsListingPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/integrations/:settingId"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <IntegrationSettingsDetailsPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/gateways"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <GatewaysPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/integration-services"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <IntegrationServicesListingPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/integration-services/:serviceId"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <IntegrationServiceFormPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/mcp"
                  handle={{ headerActions: <McpHeaderActions /> }}
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <McpListingPage />
                    </Suspense>
                  }
                />
                <Route
                  path="/mcp/:mcpId"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <McpDetailsPageWrapper />
                    </Suspense>
                  }
                />
                <Route
                  path="/members"
                  element={
                    <MembersPage />
                  }
                />
                <Route
                  path="/users"
                  handle={{ headerActions: <UsersHeaderActions /> }}
                  element={
                    <UsersPage />
                  }
                />
                <Route
                  path="/roles"
                  element={
                    <RolesPage />
                  }
                />
                <Route
                  path="*"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <NotFoundPage />
                    </Suspense>
                  }
                />
              </Route>
            </Routes>
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
    checkStreamingAvailable().then((ok) => {
      console.log('Streaming available:', ok);
      setStreamingAvailable(ok);
    });
  }, []);

  return <RouterProvider router={router} />;
}

export default App;
