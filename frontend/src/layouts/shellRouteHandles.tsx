import { HomeHeaderActions } from '@/components/HomeHeaderActions';
import { AgentsHeaderActions } from '@/components/AgentsHeaderActions';
import { McpHeaderActions } from '@/components/McpHeaderActions';
import { FlowsListHeaderActions } from '@/components/FlowsListHeaderActions';
import { KnowledgeHeaderActions } from '@/components/KnowledgeHeaderActions';
import { SkillsHeaderActions } from '@/components/skills/SkillsHeaderActions';
import { AgentPromptsHeaderActions } from '@/components/AgentPromptsHeaderActions';
import { AgentSummaryPromptsHeaderActions } from '@/components/AgentSummaryPromptsHeaderActions';
import { ExecutionProfilesHeaderActions } from '@/components/ExecutionProfilesHeaderActions';
import { SSHConnectionsHeaderActions } from '@/components/SSHConnectionsHeaderActions';
import { UsersHeaderActions } from '@/components/UsersHeaderActions';
import { DataHeaderActions } from '@/components/DataHeaderActions';
import type { AppShellRouteHandle } from '@/layouts/AppShellLayout';

const EXACT_HANDLES: Record<string, AppShellRouteHandle> = {
	'/': { hideHeader: true },
	'/dashboard': { headerActions: <HomeHeaderActions /> },
	'/agents': { headerActions: <AgentsHeaderActions /> },
	'/prompts': { headerActions: <AgentPromptsHeaderActions /> },
	'/summary-prompts': { headerActions: <AgentSummaryPromptsHeaderActions /> },
	'/execution-profiles': { headerActions: <ExecutionProfilesHeaderActions /> },
	'/ssh-connections': { headerActions: <SSHConnectionsHeaderActions /> },
	'/data': { headerActions: <DataHeaderActions /> },
	'/flows': { headerActions: <FlowsListHeaderActions /> },
	'/knowledge': { headerActions: <KnowledgeHeaderActions /> },
	'/skills': { headerActions: <SkillsHeaderActions /> },
	'/mcp': { headerActions: <McpHeaderActions /> },
	'/users': { headerActions: <UsersHeaderActions /> },
	'/playground': { hideHeader: true },
};

const PREFIX_HANDLES: Array<{ prefix: string; handle: AppShellRouteHandle }> = [
	{ prefix: '/chat', handle: { hideHeader: true } },
	{ prefix: '/playground', handle: { hideHeader: true } },
];

export function getShellRouteHandle(pathname: string): AppShellRouteHandle | undefined {
	if (EXACT_HANDLES[pathname]) {
		return EXACT_HANDLES[pathname];
	}

	for (const { prefix, handle } of PREFIX_HANDLES) {
		if (pathname === prefix || pathname.startsWith(`${prefix}/`)) {
			return handle;
		}
	}

	return undefined;
}
