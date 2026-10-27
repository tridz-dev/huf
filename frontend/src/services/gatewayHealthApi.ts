import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export type HealthEventStatus =
  | 'Received'
  | 'Rejected'
  | 'Unrouted'
  | 'Queued'
  | 'Running'
  | 'Succeeded'
  | 'Failed';

export type HealthCounts = Record<HealthEventStatus | 'total', number>;

export interface HealthEvent {
  name: string;
  status: HealthEventStatus;
  received_at: string | null;
  sender: string;
  conversation: string;
  error_message: string;
  agent_run?: string | null;
  flow_run?: string | null;
  target: string;
}

export interface GatewayHealth {
  gateway: string;
  status: {
    enabled: boolean;
    provider?: string;
    last_event_at: string | null;
    last_error: string | null;
  };
  counts: { '24h': HealthCounts; '7d': HealthCounts };
  recent_events: HealthEvent[];
  usage_7d: {
    runs: number;
    cost: number;
    total_tokens: number;
    input_tokens: number;
    output_tokens: number;
  };
}

export interface DiagnosisCheck {
  check: string;
  ok: boolean;
  plain_language_explanation: string;
  how_to_fix: string;
}

export type StatusTone = 'success' | 'warning' | 'danger' | 'neutral';

const STATUS_LABELS: Record<HealthEventStatus, string> = {
  Received: 'Received',
  Rejected: 'Blocked',
  Unrouted: 'No destination',
  Queued: 'Waiting',
  Running: 'Running',
  Succeeded: 'Done',
  Failed: 'Failed',
};

export function eventStatusLabel(status: string): string {
  return STATUS_LABELS[status as HealthEventStatus] ?? status;
}

export function eventStatusTone(status: string): StatusTone {
  switch (status) {
    case 'Succeeded':
      return 'success';
    case 'Rejected':
    case 'Unrouted':
      return 'warning';
    case 'Failed':
      return 'danger';
    default:
      return 'neutral';
  }
}

/** Events that did not result in a run and can be explained. */
export function canExplainEvent(status: string): boolean {
  return status === 'Rejected' || status === 'Unrouted' || status === 'Failed' || status === 'Received';
}

export function formatCost(cost: number): string {
  if (!cost) return '$0.00';
  return cost < 0.01 ? '<$0.01' : `$${cost.toFixed(2)}`;
}

export function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}k`;
  return String(tokens);
}

export function failedCount(counts: HealthCounts): number {
  return (counts.Failed ?? 0) + (counts.Rejected ?? 0) + (counts.Unrouted ?? 0);
}

export async function getGatewayHealth(gatewayName: string): Promise<GatewayHealth> {
  try {
    const result = await call.get('huf.ai.gateways.health.get_gateway_health', {
      gateway_name: gatewayName,
    });
    return result.message as GatewayHealth;
  } catch (error) {
    handleFrappeError(error, 'Error loading gateway activity');
  }
}

export async function diagnoseGatewayEvent(eventName: string): Promise<DiagnosisCheck[]> {
  try {
    const result = await call.get('huf.ai.gateways.health.diagnose_event', {
      event_name: eventName,
    });
    return (result.message as DiagnosisCheck[]) || [];
  } catch (error) {
    handleFrappeError(error, 'Error checking this message');
  }
}
