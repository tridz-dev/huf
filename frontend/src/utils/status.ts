export type AgentRunStatus = 'Started' | 'Queued' | 'Success' | 'Failed' | string;

export type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline';

export function getAgentRunStatusVariant(status?: AgentRunStatus): BadgeVariant {
  if (status === 'Success') return 'default';
  if (status === 'Failed') return 'destructive';
  if (status === 'Queued') return 'secondary';
  if (status === 'Started') return 'outline';
  return 'secondary';
}


