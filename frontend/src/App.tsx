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
import { McpHeaderActions } from './components/McpHeaderActions';
import { FlowsListHeaderActions } from './components/FlowsListHeaderActions';
import { HomePage } from './pages/HomePage';
import { AgentsPage } from './pages/AgentsPage';
import { AgentFormPageWrapper } from './pages/AgentFormPageWrapper';
import { FlowListPage } from './pages/FlowListPage';
import { FlowCanvasPageWrapper } from './pages/FlowCanvasPageWrapper';
import { DataPage } from './pages/DataPage';
import { IntegrationsPageWrapper } from './pages/IntegrationsPageWrapper';
import { ChatPage } from './pages/ChatPageV2';
import { NotFoundPage } from './pages/NotFoundPage';
import { Toaster } from './components/ui/sonner';
import { toast } from 'sonner';
import Executions from './pages/Executions';
import { AgentRunDetailPage } from './pages/AgentRunDetailPage';
import { useEffect } from 'react';
import { createFrappeSocket } from './utils/socket';
import {
  checkStreamingAvailable,
  setStreamingAvailable,
} from './services/streamChatApi';
import { McpDetailsPageWrapper } from './pages/McpDetailsPageWrapper';
import McpListingPage from './pages/McpListingPage';
import { PreviewViewPage } from './pages/PreviewViewPage';

function App() {
  useEffect(() => {
    // Wait for frappe.boot to be available
    const siteName = (window as any).frappe?.boot?.sitename;
    /*
     If in development, use the port set in window.frappe.boot.socketio_port for development server
     for local development with build, use the port set in frappe.boot.socketio_port.
     for production, with proper domain no port is required (think so!)
    */
    const hasPort = !!window.location?.port
    const port = hasPort ? (window as any).frappe?.boot?.socketio_port : '';

    console.log("Checking streaming availability");
    // Streaming ping: once at app load
    checkStreamingAvailable().then((ok) => {
      console.log("Streaming available:", ok);
      setStreamingAvailable(ok);
      if (!ok) {
        toast.error("Streaming not working", {
          description:
            "Some features may be disabled or not work as expected. Please refresh the page to retry.",
          duration: 5000,
        });
      }
    });

    if (!siteName) {
      toast.error("Socket connection failed", {
        description: "Some features may be disabled or not work as expected. Please refresh the page to retry.",
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
        description: "Some features may be disabled or not work as expected. Please refresh the page to retry.",
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
                    <UnifiedLayout headerActions={<FlowsListHeaderActions />}>
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
                  <UnifiedLayout hideHeader>
                    <ChatPage />
                  </UnifiedLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/chat/:chatId"
              element={
                <ProtectedRoute>
                  <UnifiedLayout hideHeader>
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
              path="/view/:messageId"
              element={
                <ProtectedRoute>
                  <PreviewViewPage />
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
