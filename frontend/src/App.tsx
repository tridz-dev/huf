import { Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { UserProvider } from './contexts/UserContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AuthenticatingPage } from './components/AuthenticatingPage';
import { FlowProvider } from './contexts/FlowContext';
import { ModalProvider } from './contexts/ModalContext';
import { UnifiedLayout } from './layouts/UnifiedLayout';
import { HomeHeaderActions } from './components/HomeHeaderActions';
import { FlowsHeaderActions } from './components/FlowsHeaderActions';
import { AgentsHeaderActions } from './components/AgentsHeaderActions';
import { DataHeaderActions } from './components/DataHeaderActions';
import { IntegrationsHeaderActions } from './components/IntegrationsHeaderActions';
import { HomePage } from './pages/HomePage';
import { AgentsPage } from './pages/AgentsPage';
import { AgentFormPageWrapper } from './pages/AgentFormPageWrapper';
import { FlowListPage } from './pages/FlowListPage';
import { FlowCanvasPageWrapper } from './pages/FlowCanvasPageWrapper';
import { DataPage } from './pages/DataPage';
import { IntegrationsPage } from './pages/IntegrationsPage';
import { ChatPage } from './pages/ChatPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { Toaster } from './components/ui/sonner';
import Executions from './pages/Executions';

function App() {
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
                <UnifiedLayout headerActions={<DataHeaderActions />}>
                  <DataPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/integrations"
            element={
              <ProtectedRoute>
                <UnifiedLayout headerActions={<IntegrationsHeaderActions />}>
                  <IntegrationsPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/flows"
            element={
              <ProtectedRoute>
                <FlowProvider>
                  <UnifiedLayout headerActions={<FlowsHeaderActions />}>
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
                <UnifiedLayout>
                  <ChatPage />
                </UnifiedLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/chat/:chatId"
            element={
              <ProtectedRoute>
                <UnifiedLayout>
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
