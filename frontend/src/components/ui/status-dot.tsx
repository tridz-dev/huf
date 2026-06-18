import { cn } from '@/lib/utils';

export type StatusType = 'running' | 'idle' | 'healthy' | 'held' | 'recording';

interface StatusDotProps {
  status: StatusType;
  className?: string;
}

const STATUS_CONFIG: Record<
  StatusType,
  { dot: boolean; blink: boolean; dotColor: string; label: string; textColor: string }
> = {
  running:   { dot: true,  blink: true,  dotColor: 'bg-signal',     label: 'Running',   textColor: 'text-ink' },
  idle:      { dot: true,  blink: false, dotColor: 'bg-steel-soft',  label: 'Idle',      textColor: 'text-steel' },
  healthy:   { dot: true,  blink: false, dotColor: 'bg-good',        label: 'Healthy',   textColor: 'text-steel' },
  held:      { dot: false, blink: false, dotColor: '',               label: 'HELD',      textColor: 'text-signal-ink' },
  recording: { dot: true,  blink: true,  dotColor: 'bg-signal',     label: 'Recording', textColor: 'text-signal-ink' },
};

export function StatusDot({ status, className }: StatusDotProps) {
  const config = STATUS_CONFIG[status];
  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      {config.dot && (
        <span
          className={cn(
            'inline-block w-1.5 h-1.5 rounded-full flex-shrink-0',
            config.dotColor,
            config.blink && 'animate-blink',
          )}
        />
      )}
      <span className={cn('font-mono text-[10.5px] uppercase tracking-wide', config.textColor)}>
        {config.label}
      </span>
    </span>
  );
}
