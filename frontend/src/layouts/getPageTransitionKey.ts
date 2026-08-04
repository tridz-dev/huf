/** Normalize pathname so related routes share one transition key (no remount fade). */
export function getPageTransitionKey(pathname: string): string {
	if (pathname.startsWith('/chat')) return '/chat';
	if (pathname.startsWith('/ui/chat')) return '/ui/chat';
	if (pathname.startsWith('/agents/')) return '/agents';
	if (pathname.startsWith('/flows/')) return '/flows';
	if (pathname.startsWith('/data/')) return '/data';
	if (pathname.startsWith('/executions/')) return '/executions';
	if (pathname.startsWith('/mcp/')) return '/mcp';
	if (pathname.startsWith('/knowledge/')) return '/knowledge';
	if (pathname.startsWith('/skills/')) return '/skills';
	if (pathname.startsWith('/memory/')) return '/memory';
	if (pathname.startsWith('/providers/')) return '/providers';
	if (pathname.startsWith('/integrations/')) return '/integrations';
	if (pathname.startsWith('/integration-services/')) return '/integration-services';
	if (pathname.startsWith('/agent-prompts/')) return '/agent-prompts';
	if (pathname.startsWith('/agent-summary-prompts/')) return '/agent-summary-prompts';
	if (pathname.startsWith('/execution-profiles/')) return '/execution-profiles';
	if (pathname.startsWith('/ssh-connections/')) return '/ssh-connections';
	return pathname;
}
