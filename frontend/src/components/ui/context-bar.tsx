import { cn } from '@/lib/utils';
import type { SegmentTokens } from '@/types/runContextMetrics.types';

export interface ContextBarCacheState {
  cacheRead: number;
  cacheWrite: number;
  uncached: number;
}

export interface ContextBarProps {
  segments: SegmentTokens;
  cacheState?: ContextBarCacheState;
  total: number;
  size?: 'sm' | 'md';
  className?: string;
  onClick?: () => void;
}

const SEGMENT_ORDER: Array<{ key: keyof SegmentTokens; label: string; color: string }> = [
  { key: 'system', label: 'System', color: 'bg-signal' },
  { key: 'tools', label: 'Tools', color: 'bg-signal' },
  { key: 'knowledge', label: 'Knowledge', color: 'bg-good' },
  { key: 'history', label: 'History', color: 'bg-warning' },
  { key: 'message', label: 'Message', color: 'bg-signal' },
];

/**
 * Segmented context/cache meter. Top strip is composition (what fills the
 * window, by tokens); bottom strip — when cacheState is supplied — is cache
 * economics (what each token cost this turn). Same component at every
 * scope: chat header (size="sm"), run detail / agent / fleet (size="md").
 */
export function ContextBar({ segments, cacheState, total, size = 'md', className, onClick }: ContextBarProps) {
  const height = size === 'sm' ? 'h-1' : 'h-2.5';
  const known = SEGMENT_ORDER.reduce((sum, { key }) => sum + (segments[key] ?? 0), 0);
  const headroom = total > known ? total - known : 0;

  const cacheTotal = cacheState ? cacheState.cacheRead + cacheState.cacheWrite + cacheState.uncached : 0;

  const Wrapper = onClick ? 'button' : 'div';

  return (
    <Wrapper
      className={cn('flex flex-col gap-1 w-full text-left', onClick && 'cursor-pointer', className)}
      onClick={onClick}
      type={onClick ? 'button' : undefined}
    >
      <div className={cn('flex w-full overflow-hidden rounded-full bg-muted', height)}>
        {SEGMENT_ORDER.map(({ key, label, color }) => {
          const value = segments[key];
          if (!value) return null;
          const pct = total > 0 ? (value / total) * 100 : 0;
          return (
            <div
              key={key}
              className={color}
              style={{ width: `${pct}%` }}
              title={`${label}: ${value.toLocaleString()} tokens`}
            />
          );
        })}
        {headroom > 0 && (
          <div
            className="bg-transparent"
            style={{ width: `${(headroom / total) * 100}%` }}
            title={`Headroom: ${headroom.toLocaleString()} tokens`}
          />
        )}
      </div>

      {cacheState && cacheTotal > 0 && (
        <div className={cn('flex w-full overflow-hidden rounded-full bg-muted', height)}>
          <div
            className="bg-signal"
            style={{ width: `${(cacheState.cacheRead / cacheTotal) * 100}%` }}
            title={`Cache read (~0.1x): ${cacheState.cacheRead.toLocaleString()} tokens`}
          />
          <div
            className="bg-warning"
            style={{ width: `${(cacheState.cacheWrite / cacheTotal) * 100}%` }}
            title={`Cache write (~1.25x): ${cacheState.cacheWrite.toLocaleString()} tokens`}
          />
          <div
            className="bg-destructive"
            style={{ width: `${(cacheState.uncached / cacheTotal) * 100}%` }}
            title={`Uncached (1x): ${cacheState.uncached.toLocaleString()} tokens`}
          />
        </div>
      )}
    </Wrapper>
  );
}
