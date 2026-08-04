import { lazy } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { FlowProvider } from '@/contexts/FlowContext';
import { ModalProvider } from '@/contexts/ModalContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { DataTableBuilderWrapper } from '@/pages/DataTableBuilderWrapper';
import { DataTableViewWrapper } from '@/pages/DataTableViewWrapper';
import { getOutletRemountKey } from '@/layouts/getPageTransitionKey';

const HomePage = lazy(() => import('@/pages/HomePage'));
const AppsPage = lazy(() => import('@/pages/AppsPage'));
const AgentsPage = lazy(() => import('@/pages/AgentsPage'));
const AgentFormPageWrapper = lazy(() => import('@/pages/AgentFormPageWrapper'));
const AgentPromptsPage = lazy(() => import('@/pages/AgentPromptsPage'));
const AgentPromptFormPageWrapper = lazy(() => import('@/pages/AgentPromptFormPageWrapper'));
const AgentSummaryPromptsPage = lazy(() => import('@/pages/AgentSummaryPromptsPage'));
const AgentSummaryPromptFormPageWrapper = lazy(
	() => import('@/pages/AgentSummaryPromptFormPageWrapper'),
);
const ExecutionProfilesPage = lazy(() => import('@/pages/ExecutionProfilesPage'));
const ExecutionProfileFormPageWrapper = lazy(() => import('@/pages/ExecutionProfileFormPageWrapper'));
const SSHConnectionsPage = lazy(() => import('@/pages/SSHConnectionsPage'));
const SSHConnectionFormPageWrapper = lazy(() => import('@/pages/SSHConnectionFormPageWrapper'));
const FlowListPage = lazy(() => import('@/pages/FlowListPage'));
const FlowCanvasPageWrapper = lazy(() => import('@/pages/FlowCanvasPageWrapper'));
const DataPage = lazy(() => import('@/pages/DataPage'));
const AiProvidersPageWrapper = lazy(() => import('@/pages/AiProvidersPageWrapper'));
const ChatPage = lazy(() => import('@/pages/ChatPageV2'));
const Executions = lazy(() => import('@/pages/Executions'));
const AgentRunDetailPageWrapper = lazy(() => import('@/pages/AgentRunDetailPageWrapper'));
const McpDetailsPageWrapper = lazy(() => import('@/pages/McpDetailsPageWrapper'));
const McpListingPage = lazy(() => import('@/pages/McpListingPage'));
const KnowledgeSourcesPage = lazy(() => import('@/pages/KnowledgeSourcesPage'));
const KnowledgeSourceFormPageWrapper = lazy(() => import('@/pages/KnowledgeSourceFormPageWrapper'));
const MemoryPage = lazy(() => import('@/pages/MemoryPage'));
const MemoryPolicyFormPageWrapper = lazy(() => import('@/pages/MemoryPolicyFormPageWrapper'));
const SkillsPage = lazy(() => import('@/pages/SkillsPage'));
const SkillFormPageWrapper = lazy(() => import('@/pages/SkillFormPageWrapper'));
const SshPage = lazy(() => import('@/pages/SshPage'));
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'));
const DataRecordViewWrapper = lazy(() => import('@/pages/DataRecordViewWrapper'));
const ModelsPageWrapper = lazy(() => import('@/pages/ModelsPageWrapper'));
const PlaygroundPage = lazy(() => import('@/pages/PlaygroundPage'));
const IntegrationSettingsListingPageWrapper = lazy(
	() => import('@/pages/IntegrationSettingsListingPageWrapper'),
);
const IntegrationSettingsDetailsPageWrapper = lazy(
	() => import('@/pages/IntegrationSettingsDetailsPageWrapper'),
);
const IntegrationServicesListingPageWrapper = lazy(
	() => import('@/pages/IntegrationServicesListingPageWrapper'),
);
const IntegrationServiceFormPageWrapper = lazy(
	() => import('@/pages/IntegrationServiceFormPageWrapper'),
);
const HubSimplePage = lazy(() => import('@/pages/HubSimplePage'));
const GatewaysPage = lazy(() => import('@/pages/GatewaysPage'));
const AgentSettingsPage = lazy(() => import('@/pages/AgentSettingsPage'));
const GeneralSettingsPage = lazy(() => import('@/pages/GeneralSettingsPage'));
const UsersPage = lazy(() => import('@/pages/UsersPage'));
const RolesPage = lazy(() => import('@/pages/RolesPage'));
const MembersPage = lazy(() => import('@/pages/MembersPage'));

function FlowLayout() {
	return (
		<FlowProvider>
			<Routes>
				<Route index element={<FlowListPage />} />
				<Route
					path=":flowId"
					element={
						<ModalProvider>
							<FlowCanvasPageWrapper />
						</ModalProvider>
					}
				/>
			</Routes>
		</FlowProvider>
	);
}

/**
 * Declarative shell routes keyed by location so list ↔ detail navigations
 * always remount the matched page. The data-router Outlet was not swapping
 * page content when the URL changed.
 */
export function ShellRoutes() {
	const location = useLocation();
	const routesKey = getOutletRemountKey(location.pathname, location.search);

	return (
		<Routes location={location} key={routesKey}>
			<Route index element={<HubSimplePage />} />
			<Route path="dashboard" element={<HomePage />} />
			<Route path="apps" element={<AppsPage />} />
			<Route path="agents" element={<AgentsPage />} />
			<Route path="agents/:id" element={<AgentFormPageWrapper />} />
			<Route path="prompts" element={<AgentPromptsPage />} />
			<Route path="prompts/:id" element={<AgentPromptFormPageWrapper />} />
			<Route path="summary-prompts" element={<AgentSummaryPromptsPage />} />
			<Route path="summary-prompts/:id" element={<AgentSummaryPromptFormPageWrapper />} />
			<Route path="execution-profiles" element={<ExecutionProfilesPage />} />
			<Route path="execution-profiles/:id" element={<ExecutionProfileFormPageWrapper />} />
			<Route path="ssh-connections" element={<SSHConnectionsPage />} />
			<Route path="ssh-connections/:id" element={<SSHConnectionFormPageWrapper />} />
			<Route path="data" element={<DataPage />} />
			<Route path="playground" element={<PlaygroundPage />} />
			<Route path="console" element={<Navigate to="/playground" replace />} />
			<Route
				path="data/new"
				element={
					<ProtectedRoute requiredCapability="data.tables.manage">
						<DataTableBuilderWrapper />
					</ProtectedRoute>
				}
			/>
			<Route path="data/:tableId" element={<DataTableViewWrapper />} />
			<Route path="data/:tableId/:recordName" element={<DataRecordViewWrapper />} />
			<Route
				path="data/:tableId/edit"
				element={
					<ProtectedRoute requiredCapability="data.tables.manage">
						<DataTableBuilderWrapper />
					</ProtectedRoute>
				}
			/>
			<Route path="models" element={<ModelsPageWrapper />} />
			<Route path="providers" element={<AiProvidersPageWrapper />} />
			<Route path="flows/*" element={<FlowLayout />} />
			<Route path="chat/:chatId?" element={<ChatPage />} />
			<Route path="executions" element={<Executions />} />
			<Route path="executions/:runId" element={<AgentRunDetailPageWrapper />} />
			<Route path="artifacts/*" element={<Navigate to="/executions" replace />} />
			<Route path="channels/*" element={<Navigate to="/gateways" replace />} />
			<Route path="settings" element={<AgentSettingsPage />} />
			<Route path="settings/general" element={<GeneralSettingsPage />} />
			<Route path="knowledge" element={<KnowledgeSourcesPage />} />
			<Route path="memory" element={<MemoryPage />} />
			<Route path="knowledge/:id" element={<KnowledgeSourceFormPageWrapper />} />
			<Route path="memory/policies/:id" element={<MemoryPolicyFormPageWrapper />} />
			<Route path="skills" element={<SkillsPage />} />
			<Route path="skills/:id" element={<SkillFormPageWrapper />} />
			<Route path="ssh" element={<SshPage />} />
			<Route path="integrations" element={<IntegrationSettingsListingPageWrapper />} />
			<Route path="integrations/:settingId" element={<IntegrationSettingsDetailsPageWrapper />} />
			<Route path="gateways" element={<GatewaysPage />} />
			<Route path="integration-services" element={<IntegrationServicesListingPageWrapper />} />
			<Route path="integration-services/:serviceId" element={<IntegrationServiceFormPageWrapper />} />
			<Route path="mcp" element={<McpListingPage />} />
			<Route path="mcp/:mcpId" element={<McpDetailsPageWrapper />} />
			<Route path="members" element={<MembersPage />} />
			<Route path="users" element={<UsersPage />} />
			<Route path="roles" element={<RolesPage />} />
			<Route path="*" element={<NotFoundPage />} />
		</Routes>
	);
}
