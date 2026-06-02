import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { UserProvider } from './contexts/UserContext';
import { PermissionsProvider } from './contexts/PermissionsContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AuthenticatingPage } from './components/AuthenticatingPage';
import { FlowProvider } from './contexts/FlowContext';
import { ModalProvider } from './contexts/ModalContext';
import { UnifiedLayout } from './layouts/UnifiedLayout';
import { HomeHeaderActions } from './components/HomeHeaderActions';
import { AgentsHeaderActions } from './components/AgentsHeaderActions';
import { FlowsListHeaderActions } from './components/FlowsListHeaderActions';
import { AgentPromptsHeaderActions } from './components/AgentPromptsHeaderActions';
import { PageLoader } from './components/PageLoader';
import { DataTableBuilderWrapper } from './pages/DataTableBuilderWrapper';
import { DataTableViewWrapper } from './pages/DataTableViewWrapper';
import { Toaster } from './components/ui/sonner';
import { toast } from 'sonner';

const HomePage = lazy(() => import('./pages/HomePage'));
const AgentsPage = lazy(() => import('./pages/AgentsPage'));
const AgentFormPageWrapper = lazy(() => import('./pages/AgentFormPageWrapper'));
const AgentPromptsPage = lazy(() => import('./pages/AgentPromptsPage'));
const AgentPromptFormPageWrapper = lazy(() => import('./pages/AgentPromptFormPageWrapper'));
const FlowListPage = lazy(() => import('./pages/FlowListPage'));
const FlowCanvasPageWrapper = lazy(() => import('./pages/FlowCanvasPageWrapper'));
const DataPage = lazy(() => import('./pages/DataPage'));
const IntegrationsPageWrapper = lazy(() => import('./pages/IntegrationsPageWrapper'));
const ChatPage = lazy(() => import('./pages/ChatPageV2'));
const Executions = lazy(() => import('./pages/Executions'));
const AgentRunDetailPage = lazy(() => import('./pages/AgentRunDetailPage'));
const McpDetailsPageWrapper = lazy(() => import('./pages/McpDetailsPageWrapper'));
const McpListingPage = lazy(() => import('./pages/McpListingPage'));
const KnowledgeSourcesPage = lazy(() => import('./pages/KnowledgeSourcesPage'));
const KnowledgeSourceFormPageWrapper = lazy(() => import('./pages/KnowledgeSourceFormPageWrapper'));
const PreviewViewPage = lazy(() => import('./pages/PreviewViewPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));
const DataRecordViewWrapper = lazy(() => import('./pages/DataRecordViewWrapper'));
const ModelsPageWrapper = lazy(() => import('./pages/ModelsPageWrapper'));
const KnowledgeLandingPage = lazy(() => import('./pages/KnowledgeLandingPage'));
const SettingsLandingPage = lazy(() => import('./pages/SettingsLandingPage'));

import { useEffect } from 'react';
import { createFrappeSocket } from './utils/socket';
import {
  checkStreamingAvailable,
  setStreamingAvailable,
} from './services/streamChatApi';
const UsersPage = lazy(() => import('./pages/UsersPage'));
const RolesPage = lazy(() => import('./pages/RolesPage'));

function App() {
  useEffect(() => {
    const connectionDescription =
      'Some features may be disabled or not work as expected. Please refresh the page to retry.';

    const siteName = (window as any).frappe?.boot?.sitename;
    const hasPort = !!window.location?.port;
    const port = hasPort ? (window as any).frappe?.boot?.socketio_port : '';

    console.log("Checking streaming availability");
    checkStreamingAvailable().then((ok) => {
      console.log("Streaming available:", ok);
      setStreamingAvailable(ok);
      if (!ok) {
        toast.error("Streaming not working", {
          description: connectionDescription,
          duration: 5000,
        });
      }
    });

    if (!siteName) {
      toast.error("Socket connection failed", {
        description: connectionDescription,
        duration: 5000,
      });
      console.warn("Site name not available yet, socket connection will be skipped");
      return;
    }

    console.log("Creating socket connection for site:", siteName);
    const socket = createFrappeSocket({ siteName, port });

    socket.on("connect", () => {
      console.log("✅ Connected to Frappe websocket!");
    });

    socket.on("connect_error", (error) => {
      console.error("❌ Socket connection error:", error);
      toast.error("Socket connection failed", {
        description: connectionDescription,
        duration: 5000,
      });
    });

    socket.on("disconnect", (reason) => {
      console.warn("⚠️ Socket disconnected:", reason);
    });

    socket.on("tool_call_started", (data) => {
      console.log("📡 Realtime event - tool_call_started:", data);
    });

    // Flow real-time events forwarding
    const flowEvents = [
      'flow_node_start',
      'flow_node_end',
      'flow_paused',
      'flow_completed',
      'flow_error'
    ];

    flowEvents.forEach(eventName => {
      socket.on(eventName, (data) => {
        console.log(`📡 Realtime event - ${eventName}:`, data);
        window.dispatchEvent(new CustomEvent(`frappe:${eventName}`, { detail: data }));
      });
    });

    return () => {
      console.log("Cleaning up socket connection");
      socket.disconnect();
    };
  }, []);


  return (
    <BrowserRouter basename="/huf">
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
          {/* Knowledge & Data Routes */}
          <Route element={<ProtectedRoute><Suspense fallback={<PageLoader />}><KnowledgeLandingPage /></Suspense></ProtectedRoute>}>
            <Route path="/knowledge" element={<Suspense fallback={<PageLoader />}><KnowledgeSourcesPage /></Suspense>} />
            <Route path="/data" element={<Suspense fallback={<PageLoader />}><DataPage /></Suspense>} />
          </Route>

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
          {/* Settings Routes */}
          <Route element={<ProtectedRoute><Suspense fallback={<PageLoader />}><SettingsLandingPage /></Suspense></ProtectedRoute>}>
            <Route path="/settings" element={<Navigate to="/providers" replace />} />
            <Route path="/providers" element={<Suspense fallback={<PageLoader />}><IntegrationsPageWrapper /></Suspense>} />
            <Route path="/models" element={<Suspense fallback={<PageLoader />}><ModelsPageWrapper /></Suspense>} />
            <Route path="/mcp" element={<Suspense fallback={<PageLoader />}><McpListingPage /></Suspense>} />
            <Route path="/users" element={<Suspense fallback={<PageLoader />}><UsersPage /></Suspense>} />
            <Route path="/roles" element={<Suspense fallback={<PageLoader />}><RolesPage /></Suspense>} />
          </Route>

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
                <UnifiedLayout>
                  <Suspense fallback={<PageLoader />}>
                    <AgentRunDetailPage />
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
    </BrowserRouter>
  );
}

export default App;