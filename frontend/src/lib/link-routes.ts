function encodeId(id: string): string {
	return encodeURIComponent(id);
}

export const linkRoutes = {
	agent: (id: string) => `/agents/${encodeId(id)}`,
	agentPrompt: (id: string) => `/prompts/${encodeId(id)}`,
	agentSummaryPrompt: (id: string) => `/summary-prompts/${encodeId(id)}`,
	executionProfile: (id: string) => `/execution-profiles/${encodeId(id)}`,
	sshConnection: (id: string) => `/ssh-connections/${encodeId(id)}`,
	knowledgeSource: (id: string) => `/knowledge/${encodeId(id)}`,
	aiModel: (id: string) => `/models?configure=${encodeId(id)}`,
	aiProvider: (id: string) => `/providers?configure=${encodeId(id)}`,
	memoryPolicy: (id: string) => `/app/memory-policy/${encodeId(id)}`,
} as const;

export type LinkRouteKey = keyof typeof linkRoutes;
