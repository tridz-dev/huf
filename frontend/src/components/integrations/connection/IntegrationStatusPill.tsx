import { AlertTriangle, CheckCircle2, CircleDashed, CircleSlash, PlugZap } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { IntegrationHealth } from '@/lib/integrations/health';

const VARIANT = {
  good: 'pill-success',
  warning: 'pill-warning',
  danger: 'pill-danger',
  neutral: 'pill-neutral',
} as const;

const ICON = {
  connected: CheckCircle2,
  active: CheckCircle2,
  attention: AlertTriangle,
  not_connected: PlugZap,
  inactive: CircleSlash,
  unchecked: CircleDashed,
} as const;

/** The one status shown for a connection: Connected, Needs attention, Not connected, Inactive. */
export function IntegrationStatusPill({ health, className }: { health: IntegrationHealth; className?: string }) {
  const Icon = ICON[health.kind];
  return (
    <Badge variant={VARIANT[health.tone]} className={className} data-testid="integration-status" data-status={health.kind}>
      <Icon className="mr-1 h-3 w-3" aria-hidden />
      {health.label}
    </Badge>
  );
}
