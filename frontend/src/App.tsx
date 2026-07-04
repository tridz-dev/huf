import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider, Routes, Route } from 'react-router-dom';
import { UserProvider } from './contexts/UserContext';
import { PermissionsProvider } from './contexts/PermissionsContext';
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
import { AgentPromptsHeaderActions } from './components/AgentPromptsHeaderActions';
import { AgentSummaryPromptsHeaderActions } from './components/AgentSummaryPromptsHeaderActions';
import { UsersHeaderActions } from './components/UsersHeaderActions';
import { PageLoader } from './components/PageLoader';
import { DataHeaderActions } from './components/DataHeaderActions';
import { DataTableBuilderWrapper } from './pages/DataTableBuilderWrapper';
import { DataTableViewWrapper } from './pages/DataTableViewWrapper';
import { Toaster } from './components/ui/sonner';
import { toast } from 'sonner';

const HomePage = lazy(() => import('./pages/HomePage'));
const AgentsPage = lazy(() => import('./pages/AgentsPage'));
const AgentFormPageWrapper = lazy(() => import('./pages/AgentFormPageWrapper'));
const AgentPromptsPage = lazy(() => import('./pages/AgentPromptsPage'));
const AgentPromptFormPageWrapper = lazy(() => import('./pages/AgentPromptFormPageWrapper'));
const AgentSummaryPromptsPage = lazy(() => import('./pages/AgentSummaryPromptsPage'));
const AgentSummaryPromptFormPageWrapper = lazy(() => import('./pages/AgentSummaryPromptFormPageWrapper'));
const FlowListPage = lazy(() => import('./pages/FlowListPage'));
const FlowCanvasPageWrapper = lazy(() => import('./pages/FlowCanvasPageWrapper'));
const DataPage = lazy(() => import('./pages/DataPage'));
const AiProvidersPageWrapper = lazy(() => import('./pages/AiProvidersPageWrapper'));
const ChatPage = lazy(() => import('./pages/ChatPageV2'));
const Executions = lazy(() => import('./pages/Executions'));
const AgentRunDetailPageWrapper = lazy(() => import('./pages/AgentRunDetailPageWrapper'));
const AgentContextArtifactsPage = lazy(() => import('./pages/AgentContextArtifactsPage'));
const AgentContextArtifactDetailPage = lazy(() => import('./pages/AgentContextArtifactDetailPage'));
const McpDetailsPageWrapper = lazy(() => import('./pages/McpDetailsPageWrapper'));
const McpListingPage = lazy(() => import('./pages/McpListingPage'));
const KnowledgeSourcesPage = lazy(() => import('./pages/KnowledgeSourcesPage'));
const KnowledgeSourceFormPageWrapper = lazy(() => import('./pages/KnowledgeSourceFormPageWrapper'));
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

import { useEffect } from 'react';
import { SocketProvider } from './contexts/SocketContext';
import {
  checkStreamingAvailable,
  setStreamingAvailable,
} from './services/streamChatApi';
const UsersPage = lazy(() => import('./pages/UsersPage'));
const RolesPage = lazy(() => import('./pages/RolesPage'));

function AppShell() {
  return (
    <SocketProvider>
      <UserProvider>
        <PermissionsProvider>
          <Suspense fallback={<AuthenticatingPage />}>
            <Routes>
          <Route
            path="/"
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
              <ProtectedRoute>
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
              <ProtectedRoute>
                <DataTableBuilderWrapper />
              </ProtectedRoute>
            }
          />
          <Route
            path="/models"
            element={
              <ProtectedRoute capability="system.models.manage">
                <Suspense fallback={<PageLoader />}>
                  <ModelsPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/providers"
            element={
              <ProtectedRoute capability="system.providers.manage">
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
                    <NotFoundPage />
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
            path="/integrations"
            element={
              <ProtectedRoute capability="system.integrations.manage">
                <Suspense fallback={<PageLoader />}>
                  <IntegrationSettingsListingPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/integrations/:settingId"
            element={
              <ProtectedRoute capability="system.integrations.manage">
                <Suspense fallback={<PageLoader />}>
                  <IntegrationSettingsDetailsPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
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
              <ProtectedRoute capability="system.mcp.manage">
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
              <ProtectedRoute capability="system.mcp.manage">
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
              <ProtectedRoute capability="users.manage">
                <UnifiedLayout headerActions={<UsersHeaderActions />}>
                  <UsersPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/roles"
            element={
              <ProtectedRoute capability="roles.manage">
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
          </Suspense>
          <Toaster />
        </PermissionsProvider>
      </UserProvider>
    </SocketProvider>
  );
}

const router = createBrowserRouter(
  [{ path: '*', element: <AppShell /> }],
  { basename: '/huf' },
);

function App() {
  useEffect(() => {
    console.log("Checking streaming availability");
    checkStreamingAvailable().then((ok) => {
      console.log("Streaming available:", ok);
      setStreamingAvailable(ok);
      if (!ok) {
        toast.error("Streaming not working", {
          description: 'Some features may be disabled or not work as expected. Please refresh the page to retry.',
          duration: 5000,
        });
      }
    });
  }, []);

  return <RouterProvider router={router} />;
}

export default App;