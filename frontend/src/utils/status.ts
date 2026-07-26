export type AgentRunStatus = 'Started' | 'Queued' | 'Success' | 'Failed' | string;

export type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'success' | 'outline';

export function getAgentRunStatusVariant(status?: AgentRunStatus): BadgeVariant {
  const normalized = status?.toLowerCase();
  if (normalized === 'success') return 'success';
  if (normalized === 'failed') return 'destructive';
  if (status === 'Queued') return 'secondary';
  if (status === 'Started') return 'outline';
  return 'secondary';
}


