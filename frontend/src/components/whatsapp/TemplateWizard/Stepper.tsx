import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';

export const STEP_TITLES = ['Pick a type', 'Write it', 'Check and send'] as const;

interface Props {
  current: number;
  /** Steps that cannot be revisited (edit mode skips the first). */
  lockedBefore?: number;
  onGo: (step: number) => void;
}

export function Stepper({ current, lockedBefore = 0, onGo }: Props) {
  return (
    <ol className="flex flex-wrap items-center gap-x-3 gap-y-2" aria-label="Progress">
      {STEP_TITLES.map((title, i) => {
        const done = i < current;
        const canGo = done && i >= lockedBefore;
        const body = (
          <>
            <span
              className={cn(
                'flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-medium',
                i === current && 'border-ink bg-ink text-primary-foreground',
                done && 'border-signal bg-signal/15 text-signal-ink',
                i > current && 'border-line text-steel',
              )}
            >
              {done ? <Check className="h-3.5 w-3.5" aria-hidden /> : i + 1}
            </span>
            <span className={cn('text-sm', i === current ? 'font-medium text-ink' : 'text-steel')}>{title}</span>
          </>
        );
        return (
          <li key={title} className="flex items-center gap-3" aria-current={i === current ? 'step' : undefined}>
            {canGo ? (
              <button type="button" className="flex items-center gap-2 rounded-sm focus-visible:ring-1 focus-visible:ring-ring" onClick={() => onGo(i)}>
                {body}
              </button>
            ) : (
              <span className="flex items-center gap-2">{body}</span>
            )}
            {i < STEP_TITLES.length - 1 && <span className="hidden h-px w-8 bg-line sm:block" aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}
