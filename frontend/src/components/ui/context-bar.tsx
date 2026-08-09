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
  /** Render a visible swatch legend below the bars (run detail context panel). */
  showLegend?: boolean;
  className?: string;
  onClick?: () => void;
}

/**
 * Cache economics ramp. Red would read as failure, so cached and uncached
 * tokens share the neutral ramp and only cache reads get the accent.
 */
const CACHE_READ_COLOR = 'bg-signal';
const CACHE_WRITE_COLOR = 'bg-steel';
const UNCACHED_COLOR = 'bg-steel-soft';
const FREE_COLOR = 'bg-muted';

function LegendSwatch({ color }: { color: string }) {
  return <span aria-hidden className={cn('inline-block h-[7px] w-[7px] rounded-[1px] shrink-0', color)} />;
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
export function ContextBar({
  segments,
  cacheState,
  total,
  size = 'md',
  showLegend = false,
  className,
  onClick,
}: ContextBarProps) {
  const height = size === 'sm' ? 'h-1' : 'h-2';
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
            className={CACHE_READ_COLOR}
            style={{ width: `${(cacheState.cacheRead / cacheTotal) * 100}%` }}
            title={`Cache read (~0.1x): ${cacheState.cacheRead.toLocaleString()} tokens`}
          />
          <div
            className={CACHE_WRITE_COLOR}
            style={{ width: `${(cacheState.cacheWrite / cacheTotal) * 100}%` }}
            title={`Cache write (~1.25x): ${cacheState.cacheWrite.toLocaleString()} tokens`}
          />
          <div
            className={UNCACHED_COLOR}
            style={{ width: `${(cacheState.uncached / cacheTotal) * 100}%` }}
            title={`Fresh input (1x): ${cacheState.uncached.toLocaleString()} tokens`}
          />
        </div>
      )}

      {showLegend && cacheState && cacheTotal > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-0.5 text-[11px] text-steel">
          <span className="flex items-center gap-1.5">
            <LegendSwatch color={CACHE_READ_COLOR} />
            Cache reads {formatPct(cacheState.cacheRead / cacheTotal)}
          </span>
          {cacheState.cacheWrite > 0 && (
            <span className="flex items-center gap-1.5">
              <LegendSwatch color={CACHE_WRITE_COLOR} />
              Cache writes {formatPct(cacheState.cacheWrite / cacheTotal)}
            </span>
          )}
          <span className="flex items-center gap-1.5">
            <LegendSwatch color={UNCACHED_COLOR} />
            Fresh input {formatPct(cacheState.uncached / cacheTotal)}
          </span>
          <span className="flex items-center gap-1.5">
            <LegendSwatch color={cn(FREE_COLOR, 'border border-line')} />
            Window free {total > 0 ? formatPct(headroom / total) : '0%'}
          </span>
        </div>
      )}
    </Wrapper>
  );
}

function formatPct(ratio: number) {
  if (!Number.isFinite(ratio) || ratio <= 0) return '0%';
  return `${Math.round(ratio * 100)}%`;
}
