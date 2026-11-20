/**
 * FilterPills (DESIGN.md §6.10.3): a single-choice row of status filters with
 * counts. Behaves as a radio group: one pill is always selected, arrow keys
 * move between pills. A pill with a tone shows its count in that tone (use
 * `attention` for "Needs attention"); a pill with count 0 stays visible
 * unless `hideEmpty` is set, so the row does not jump.
 */
import { useRef, type KeyboardEvent } from 'react';
import { cn } from '@/lib/utils';
import { TONE_TEXT, type Tone } from './tones';

export interface FilterPill<V extends string = string> {
  value: V;
  label: string;
  count?: number;
  tone?: Tone;
  hideEmpty?: boolean;
}

export interface FilterPillsProps<V extends string = string> {
  pills: FilterPill<V>[];
  value: V;
  onChange: (value: V) => void;
  /** Accessible name for the group, e.g. "Filter by status". */
  label?: string;
  className?: string;
}

export function FilterPills<V extends string = string>({
  pills,
  value,
  onChange,
  label = 'Filter',
  className,
}: FilterPillsProps<V>) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const shown = pills.filter((p) => !(p.hideEmpty && !p.count) || p.value === value);

  const onKey = (e: KeyboardEvent, i: number) => {
    const dir = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    const next = (i + dir + shown.length) % shown.length;
    onChange(shown[next].value);
    refs.current[next]?.focus();
  };

  return (
    <div role="radiogroup" aria-label={label} className={cn('flex flex-wrap items-center gap-1.5', className)}>
      {shown.map((p, i) => {
        const on = p.value === value;
        return (
          <button
            key={p.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            data-state={on ? 'on' : 'off'}
            onClick={() => onChange(p.value)}
            onKeyDown={(e) => onKey(e, i)}
            className={cn(
              'inline-flex h-control-sm items-center gap-1.5 rounded-full border px-3 text-micro transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              on ? 'border-ink bg-ink text-primary-foreground' : 'border-line bg-panel text-steel hover:text-ink',
            )}
          >
            {p.label}
            {p.count !== undefined && (
              <span
                data-testid="filter-count"
                className={cn('font-mono text-meta', on ? 'text-primary-foreground/80' : p.tone ? TONE_TEXT[p.tone] : 'text-steel-soft')}
              >
                {p.count.toLocaleString()}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
