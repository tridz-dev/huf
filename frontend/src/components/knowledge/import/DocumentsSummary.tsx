import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { Health, HealthKey } from './ingestionLabels';

const HEALTH_VARIANT: Record<HealthKey, 'pill-success' | 'pill-info' | 'pill-warning' | 'pill-neutral' | 'pill-danger'> = {
  ready: 'pill-success',
  updating: 'pill-info',
  attention: 'pill-warning',
  empty: 'pill-neutral',
  broken: 'pill-danger',
  paused: 'pill-neutral',
};

export function HealthBadge({ health, className }: { health: Health; className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={className} data-testid="health-badge">
          <Badge variant={HEALTH_VARIANT[health.key]}>{health.label}</Badge>
        </span>
      </TooltipTrigger>
      <TooltipContent>{health.hint}</TooltipContent>
    </Tooltip>
  );
}
