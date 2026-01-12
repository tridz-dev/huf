import { Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { UserProvider } from './contexts/UserContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AuthenticatingPage } from './components/AuthenticatingPage';
import { FlowProvider } from './contexts/FlowContext';
import { ModalProvider } from './contexts/ModalContext';
import { UnifiedLayout } from './layouts/UnifiedLayout';
import { HomeHeaderActions } from './components/HomeHeaderActions';
import { AgentsHeaderActions } from './components/AgentsHeaderActions';
import { ChatHeaderActions } from './components/ChatHeaderActions';
import { McpHeaderActions } from './components/McpHeaderActions';
import { HomePage } from './pages/HomePage';
import { AgentsPage } from './pages/AgentsPage';
import { AgentFormPageWrapper } from './pages/AgentFormPageWrapper';
import { FlowListPage } from './pages/FlowListPage';
import { FlowCanvasPageWrapper } from './pages/FlowCanvasPageWrapper';
import { DataPage } from './pages/DataPage';
import { IntegrationsPageWrapper } from './pages/IntegrationsPageWrapper';
import { ChatPage } from './pages/ChatPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { Toaster } from './components/ui/sonner';
import Executions from './pages/Executions';
import { AgentRunDetailPage } from './pages/AgentRunDetailPage';
import { useEffect } from 'react';
import { createFrappeSocket } from './utils/socket';
import { McpDetailsPageWrapper } from './pages/McpDetailsPageWrapper';
import McpListingPage from './pages/McpListingPage';

function App() {
  useEffect(() => {
    // Wait for frappe.boot to be available
    const siteName = (window as any).frappe?.boot?.sitename;
    const port = (window as any).frappe?.boot?.socketio_port;
    
    if (!siteName) {
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
    });

    socket.on("disconnect", (reason) => {
      console.warn("⚠️ Socket disconnected:", reason);
    });

    socket.on("tool_call_started", (data) => {
      console.log("📡 Realtime event - tool_call_started:", data);
    });

    return () => {
      console.log("Cleaning up socket connection");
      socket.disconnect();
    };
  }, []);


  return (
    <BrowserRouter basename="/huf">
      <UserProvider>
        <Suspense fallback={<AuthenticatingPage />}>
          <Routes>
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<HomeHeaderActions />}>
                  <HomePage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/agents"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<AgentsHeaderActions />}>
                  <AgentsPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/agents/:id"
            element={
              <ProtectedRoute>
                <AgentFormPageWrapper />
              </ProtectedRoute>
            }
          />
          <Route
            path="/data"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <DataPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/providers"
            element={
              <ProtectedRoute>
                <IntegrationsPageWrapper />
              </ProtectedRoute>
            }
          />
          <Route
            path="/flows"
            element={
              <ProtectedRoute>
                <FlowProvider>
                  <UnifiedLayout>
                    <FlowListPage />
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
                    <FlowCanvasPageWrapper />
                  </ModalProvider>
                </FlowProvider>
              </ProtectedRoute>
            }
          />
          <Route
            path="/chat"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<ChatHeaderActions />}>
                  <ChatPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/chat/:chatId"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<ChatHeaderActions />}>
                  <ChatPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/executions"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <Executions />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/executions/:runId"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <AgentRunDetailPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <NotFoundPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/help"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <NotFoundPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/mcp"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<McpHeaderActions />}>
                  <McpListingPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/mcp/:mcpId"
            element={
              <ProtectedRoute>
                <McpDetailsPageWrapper />
              </ProtectedRoute>
            }
          />
          <Route
            path="*"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
                  <NotFoundPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          </Routes>
        </Suspense>
        <Toaster />
      </UserProvider>
    </BrowserRouter>
  );
}

export default App;
