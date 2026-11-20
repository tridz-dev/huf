/**
 * Shared tone vocabulary for the resource-page patterns (DESIGN.md §6.10, §7).
 *
 * A tone is the meaning, never a colour: callers pick `ready`, `live`,
 * `attention`, `off` or `error`, and the token mapping lives only here.
 * `live` is the only tone that moves (the §8 blink).
 */
import { cn } from '@/lib/utils';

export type Tone = 'ready' | 'live' | 'attention' | 'off' | 'error' | 'neutral';

export const TONE_DOT: Record<Tone, string> = {
  ready: 'bg-good',
  live: 'bg-signal motion-safe:animate-blink',
  attention: 'bg-warning',
  off: 'bg-steel-soft',
  error: 'bg-destructive',
  neutral: 'bg-steel-soft',
};

export const TONE_TEXT: Record<Tone, string> = {
  ready: 'text-good',
  live: 'text-signal-ink',
  attention: 'text-warning',
  off: 'text-steel',
  error: 'text-destructive',
  neutral: 'text-steel',
};

/** The bare 6px status dot. Decorative: the adjacent text carries the meaning. */
export function ToneDot({ tone, className }: { tone: Tone; className?: string }) {
  return (
    <span
      aria-hidden="true"
      data-tone={tone}
      className={cn('inline-block h-1.5 w-1.5 shrink-0 rounded-full', TONE_DOT[tone], className)}
    />
  );
}
