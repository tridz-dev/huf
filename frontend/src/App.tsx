import { BrowserRouter, Routes, Route } from 'react-router-dom';
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

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={
            <UnifiedLayout headerActions={<HomeHeaderActions />}>
              <HomePage />
            </UnifiedLayout>
          }
        />
        <Route
          path="/agents"
          element={
            <UnifiedLayout headerActions={<AgentsHeaderActions />}>
              <AgentsPage />
            </UnifiedLayout>
          }
        />
        <Route
          path="/agents/:id"
          element={<AgentFormPageWrapper />}
        />
        <Route
          path="/data"
          element={
            <UnifiedLayout headerActions={<DataHeaderActions />}>
              <DataPage />
            </UnifiedLayout>
          }
        />
        <Route
          path="/integrations"
          element={
            <UnifiedLayout headerActions={<IntegrationsHeaderActions />}>
              <IntegrationsPage />
            </UnifiedLayout>
          }
        />
        <Route path="/flows" element={
          <FlowProvider>
            <UnifiedLayout headerActions={<FlowsHeaderActions />}>
              <FlowListPage />
            </UnifiedLayout>
          </FlowProvider>
        } />
        <Route path="/flows/:flowId" element={
          <FlowProvider>
            <ModalProvider>
              <FlowCanvasPageWrapper />
            </ModalProvider>
          </FlowProvider>
        } />
        <Route
          path="/chat"
          element={
            <UnifiedLayout>
              <ChatPage />
            </UnifiedLayout>
          }
        />
        <Route path="/settings" element={<UnifiedLayout><NotFoundPage /></UnifiedLayout>} />
        <Route path="/help" element={<UnifiedLayout><NotFoundPage /></UnifiedLayout>} />
        <Route path="*" element={
          <UnifiedLayout>
            <NotFoundPage />
          </UnifiedLayout>
        } />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
