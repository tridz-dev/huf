import { paletteIcon } from '@/components/nodes/nodeIcons';
import { stepInfo } from '@/lib/flow/flowListSummary';
import type { FlowCardStep } from '@/services/flowCardsApi';
import { cn } from '@/lib/utils';

interface FlowStepStripProps {
  steps: FlowCardStep[];
  /** Total number of steps when more than `steps` are known (the list caps what it sends). */
  total?: number;
  /** How many icons to draw before "+N". */
  max?: number;
  className?: string;
  'data-testid'?: string;
}

/** A row of small step icons: a quick picture of what a flow does, without any engine words. */
export function FlowStepStrip({ steps, total, max = 6, className, 'data-testid': testId }: FlowStepStripProps) {
  if (steps.length === 0) return null;
  const shown = steps.slice(0, max);
  const hidden = Math.max((total ?? steps.length) - shown.length, 0);
  return (
    <div className={cn('flex items-center gap-1', className)} data-testid={testId} aria-label={`Steps: ${steps.map((s) => stepInfo(s).name).join(', ')}`}>
      {shown.map((step, i) => {
        const info = stepInfo(step);
        const Icon = paletteIcon(info.icon);
        return (
          <span
            key={i}
            title={info.name}
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-line bg-background text-steel"
            data-step-icon={info.icon}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden />
          </span>
        );
      })}
      {hidden > 0 && <span className="pl-0.5 text-xs text-steel">+{hidden}</span>}
    </div>
  );
}
