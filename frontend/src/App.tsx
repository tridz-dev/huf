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
import { PageLoader } from './components/PageLoader';
import { DataHeaderActions } from './components/DataHeaderActions';
import { MeetingsHeaderActions } from './components/meetings/MeetingsHeaderActions';
import { DataTableBuilderWrapper } from './pages/DataTableBuilderWrapper';
import { DataTableViewWrapper } from './pages/DataTableViewWrapper';
import { Toaster } from './components/ui/sonner';
import { CommandPalette } from './components/CommandPalette';

const HomePage = lazy(() => import('./pages/HomePage'));
const AppsPage = lazy(() => import('./pages/AppsPage'));
const AgentsPage = lazy(() => import('./pages/AgentsPage'));
const AgentFormPageWrapper = lazy(() => import('./pages/AgentFormPageWrapper'));
const AutomationFormPageWrapper = lazy(() => import('./pages/AutomationFormPageWrapper'));
const AutomationsPage = lazy(() => import('./pages/AutomationsPage'));
const AgentPromptsPage = lazy(() => import('./pages/AgentPromptsPage'));
const AgentPromptFormPageWrapper = lazy(() => import('./pages/AgentPromptFormPageWrapper'));
const AgentSummaryPromptsPage = lazy(() => import('./pages/AgentSummaryPromptsPage'));
const AgentSummaryPromptFormPageWrapper = lazy(() => import('./pages/AgentSummaryPromptFormPageWrapper'));
const ExecutionProfilesPage = lazy(() => import('./pages/ExecutionProfilesPage'));
const ExecutionProfileFormPageWrapper = lazy(() => import('./pages/ExecutionProfileFormPageWrapper'));
const SSHConnectionsPage = lazy(() => import('./pages/SSHConnectionsPage'));
const SSHConnectionFormPageWrapper = lazy(() => import('./pages/SSHConnectionFormPageWrapper'));
const NetworkAccessPoliciesPage = lazy(() => import('./pages/NetworkAccessPoliciesPage'));
const NetworkAccessPolicyFormPage = lazy(() => import('./pages/NetworkAccessPolicyFormPage'));
const FlowListPage = lazy(() => import('./pages/FlowListPage'));
const FlowCanvasPageWrapper = lazy(() => import('./pages/FlowCanvasPageWrapper'));
const DataPage = lazy(() => import('./pages/DataPage'));
const AiProvidersPageWrapper = lazy(() => import('./pages/AiProvidersPageWrapper'));
const ChatPage = lazy(() => import('./pages/ChatPageV2'));
const ChatOnlyPage = lazy(() => import('./pages/ChatOnlyPage'));
const ChatProjectsPage = lazy(() =>
  import('./pages/chat/ChatProjectsPage').then((m) => ({ default: m.ChatProjectsPage }))
);
const ChatProjectPage = lazy(() => import('./pages/chat/ChatProjectPage'));
const ChatArtifactsPage = lazy(() =>
  import('./pages/chat/ChatPlaceholderPages').then((m) => ({ default: m.ChatArtifactsPage }))
);
const ChatScheduledPage = lazy(() =>
  import('./pages/chat/ChatPlaceholderPages').then((m) => ({ default: m.ChatScheduledPage }))
);
const Executions = lazy(() => import('./pages/Executions'));
const AnalyticsEntityDetailPage = lazy(() => import('./pages/AnalyticsEntityDetailPage'));
const AgentRunDetailPageWrapper = lazy(() => import('./pages/AgentRunDetailPageWrapper'));
const AgentContextArtifactsPage = lazy(() => import('./pages/AgentContextArtifactsPage'));
const AgentContextArtifactDetailPageWrapper = lazy(
  () => import('./pages/AgentContextArtifactDetailPageWrapper')
);
const AgentProceduresPage = lazy(() => import('./pages/AgentProceduresPage'));
const AgentProcedureDetailPageWrapper = lazy(
  () => import('./pages/AgentProcedureDetailPageWrapper')
);
const McpDetailsPageWrapper = lazy(() => import('./pages/McpDetailsPageWrapper'));
const McpListingPage = lazy(() => import('./pages/McpListingPage'));
const MeetingsPage = lazy(() => import('./pages/MeetingsPage'));
const MeetingRecorderPage = lazy(() => import('./pages/MeetingRecorderPage'));
const MeetingDetailPageWrapper = lazy(() => import('./pages/MeetingDetailPageWrapper'));
const KnowledgeSourcesPage = lazy(() => import('./pages/KnowledgeSourcesPage'));
const KnowledgeSourceFormPageWrapper = lazy(() => import('./pages/KnowledgeSourceFormPageWrapper'));
const MemoryPage = lazy(() => import('./pages/MemoryPage'));
const MemoryPolicyFormPageWrapper = lazy(() => import('./pages/MemoryPolicyFormPageWrapper'));
const SkillsPage = lazy(() => import('./pages/SkillsPage'));
const SkillFormPageWrapper = lazy(() => import('./pages/SkillFormPageWrapper'));
const SshPage = lazy(() => import('./pages/SshPage'));
const PreviewViewPage = lazy(() => import('./pages/PreviewViewPage'));
const ArtifactViewPage = lazy(() => import('./pages/ArtifactViewPage'));
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
const GatewayDetailsPageWrapper = lazy(
  () => import('./pages/GatewayDetailsPageWrapper'),
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

import { useEffect } from 'react';
import { RouteErrorBoundary, clearChunkReloadFlag } from './components/RouteErrorBoundary';
import { initTheme } from './lib/personalization';
import { SocketProvider } from './contexts/SocketContext';
import {
  checkStreamingAvailable,
  setStreamingAvailable,
} from './services/streamChatApi';
const MembersPage = lazy(() => import('./pages/MembersPage'));
const HufRoleFormPage = lazy(() => import('./pages/HufRoleFormPage'));

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

  useEffect(() => {
    initTheme();
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
                <UnifiedLayout hideHeader>
                  <Suspense fallback={<PageLoader />}>
                    <HubSimplePage />
                  </Suspense>
                </UnifiedLayout>
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
            path="/automations"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <AutomationsPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/automations/:automationId"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <AutomationFormPageWrapper />
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
            path="/network-policies"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <NetworkAccessPoliciesPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/network-policies/:id"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <NetworkAccessPolicyFormPage />
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
            path="/playground"
            element={
              <ProtectedRoute>
                <UnifiedLayout hideHeader>
                  <Suspense fallback={<PageLoader />}>
                    <PlaygroundPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
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
                <UnifiedLayout hideHeader hideRail>
                  <Suspense fallback={<PageLoader />}>
                    <ChatPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/chat/projects"
            element={
              <ProtectedRoute>
                <UnifiedLayout hideHeader hideRail>
                  <Suspense fallback={<PageLoader />}>
                    <ChatProjectsPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/chat/projects/:projectId"
            element={
              <ProtectedRoute>
                <UnifiedLayout hideHeader hideRail>
                  <Suspense fallback={<PageLoader />}>
                    <ChatProjectPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/chat/artifacts"
            element={
              <ProtectedRoute>
                <UnifiedLayout hideHeader hideRail>
                  <Suspense fallback={<PageLoader />}>
                    <ChatArtifactsPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/chat/scheduled"
            element={
              <ProtectedRoute>
                <UnifiedLayout hideHeader hideRail>
                  <Suspense fallback={<PageLoader />}>
                    <ChatScheduledPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/chat/:chatId"
            element={
              <ProtectedRoute>
                <UnifiedLayout hideHeader hideRail>
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
          <Route path="/analytics" element={<Navigate to="/executions?tab=analytics" replace />} />
          <Route
            path="/analytics/:dimension/:entity"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <AnalyticsEntityDetailPage />
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
                <Suspense fallback={<PageLoader />}>
                  <AgentContextArtifactDetailPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route path="/artifacts/*" element={<Navigate to="/artifacts" replace />} />
          <Route
            path="/procedures"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <AgentProceduresPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/procedures/:procedureId"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <AgentProcedureDetailPageWrapper />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route path="/procedures/*" element={<Navigate to="/procedures" replace />} />
          <Route path="/channels/*" element={<Navigate to="/gateways" replace />} />
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
            path="/settings/general"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <GeneralSettingsPage />
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
            path="/memory/policies/:id"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <MemoryPolicyFormPageWrapper />
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
          <Route
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
          />
          <Route
            path="/gateways/:settingId"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <GatewayDetailsPageWrapper />
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
            path="/meetings"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<MeetingsHeaderActions />}>
                  <Suspense fallback={<PageLoader />}>
                    <MeetingsPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/meetings/:meetingId/record"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <MeetingRecorderPage />
                  </Suspense>
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/meetings/:meetingId"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <MeetingDetailPageWrapper />
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
            path="/artifact/:artifactId"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <ArtifactViewPage />
                </Suspense>
              </ProtectedRoute>
            }
          />
          <Route
            path="/members"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <MembersPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route path="/users" element={<Navigate to="/members" replace />} />
          <Route
            path="/roles"
            element={<Navigate to="/members?view=roles" replace />}
          />
          <Route
            path="/roles/:id"
            element={
              <ProtectedRoute>
                <Suspense fallback={<PageLoader />}>
                  <HufRoleFormPage />
                </Suspense>
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
          <CommandPalette />
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
