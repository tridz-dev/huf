/**
 * StatusSentence (DESIGN.md §6.10.2): one dot + one plain sentence + an
 * optional inline action. It answers "what state is this collection in?"
 * in words, e.g. "Ready · 1,241 items · used by 2 agents".
 */
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { ToneDot, type Tone } from './tones';

export interface StatusSentenceProps {
  tone: Tone;
  /** Plain sentence. Segments are joined with " · ". Falsy segments are dropped. */
  children?: ReactNode;
  parts?: Array<ReactNode | false | null | undefined>;
  /** Optional inline action rendered as a link-style button after the sentence. */
  action?: { label: string; onClick: () => void };
  /** Announce changes politely (use while the state is changing, e.g. importing). */
  live?: boolean;
  className?: string;
}

export function StatusSentence({ tone, children, parts, action, live, className }: StatusSentenceProps) {
  const segments = (parts ?? []).filter((p) => p !== false && p !== null && p !== undefined && p !== '');
  return (
    <span
      data-testid="status-sentence"
      data-tone={tone}
      role={live ? 'status' : undefined}
      aria-live={live ? 'polite' : undefined}
      className={cn('inline-flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-ui-text text-steel', className)}
    >
      <ToneDot tone={tone} />
      <span className="min-w-0">
        {children}
        {segments.map((s, i) => (
          <span key={i}>
            {(i > 0 || children) && <span aria-hidden="true"> · </span>}
            {s}
          </span>
        ))}
      </span>
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="rounded-sm text-signal-ink underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {action.label}
        </button>
      )}
    </span>
  );
}
