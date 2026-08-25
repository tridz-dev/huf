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

export type BatchJobStatus =
  | 'Pending'
  | 'Submitted'
  | 'In Progress'
  | 'Completed'
  | 'Failed'
  | 'Cancelled'
  | 'Expired'
  | string;

/** Badge color mapping for Batch Job status, following the same scheme as agent runs. */
export function getBatchJobStatusVariant(status?: BatchJobStatus): BadgeVariant {
  const normalized = status?.toLowerCase();
  if (normalized === 'completed') return 'success';
  if (normalized === 'failed' || normalized === 'expired') return 'destructive';
  if (normalized === 'cancelled') return 'secondary';
  if (normalized === 'in progress' || normalized === 'submitted') return 'outline';
  return 'secondary';
}


