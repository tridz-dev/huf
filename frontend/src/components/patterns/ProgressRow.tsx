/**
 * ProgressRow (DESIGN.md §6.10.5): a long-running job shown in place, as a
 * row at the top of the list it is filling, not as a card or a toast.
 *
 *   determinate:   "Importing from S3 · bucket/ — 1,240 of 3,000 · about 2 min left   Cancel"
 *   indeterminate: "Finding files in S3 · bucket/ — 412 found so far                 Cancel"
 *
 * `total` unknown (undefined or 0) means indeterminate: no bar fill, the live
 * dot blinks, and the count reads "N found so far". The row is a polite live
 * region and exposes role="progressbar" with aria-valuenow when determinate.
 */
import type { ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { ToneDot } from './tones';

export interface ProgressRowProps {
  /** Verb phrase, e.g. "Importing" or "Finding files". */
  label: string;
  /** Where the work comes from, e.g. "S3 · kq-bucket/corpus/". */
  source?: ReactNode;
  /** Items finished (determinate) or found so far (indeterminate). */
  done?: number;
  /** Total items. Undefined or 0 = not known yet (indeterminate). */
  total?: number;
  /** Noun for found-so-far copy, plural. Default "items". */
  noun?: string;
  /** Plain ETA, e.g. "about 2 min left". Never shown when indeterminate. */
  eta?: string;
  onCancel?: () => void;
  cancelLabel?: string;
  /** Extra action, e.g. "View details". */
  secondary?: { label: string; onClick: () => void };
  className?: string;
}

const fmt = (n: number) => n.toLocaleString();

export function progressCopy({ done = 0, total, noun = 'items', eta }: Pick<ProgressRowProps, 'done' | 'total' | 'noun' | 'eta'>): string {
  if (!total) return done > 0 ? `${fmt(done)} ${noun} found so far` : 'Starting…';
  return [`${fmt(Math.min(done, total))} of ${fmt(total)}`, eta].filter(Boolean).join(' · ');
}

export function ProgressRow({
  label,
  source,
  done = 0,
  total,
  noun,
  eta,
  onCancel,
  cancelLabel = 'Cancel',
  secondary,
  className,
}: ProgressRowProps) {
  const determinate = Boolean(total && total > 0);
  const percent = determinate ? Math.min(100, Math.round((done / (total as number)) * 100)) : 0;
  const copy = progressCopy({ done, total, noun, eta: determinate ? eta : undefined });
  return (
    <div
      data-testid="progress-row"
      data-mode={determinate ? 'determinate' : 'indeterminate'}
      className={cn('border-b border-line bg-paper-deep px-4 py-3', className)}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-ui-text">
        <ToneDot tone="live" />
        <span role="status" aria-live="polite" className="min-w-0 text-ink">
          <span className="font-medium">
            {label}
            {source && <> from {source}</>}
          </span>
          <span className="text-steel"> — {copy}</span>
        </span>
        <span className="flex-1" />
        {secondary && (
          <Button type="button" variant="ghost" size="sm" onClick={secondary.onClick}>
            {secondary.label}
          </Button>
        )}
        {onCancel && (
          <Button type="button" variant="link" size="sm" onClick={onCancel}>
            {cancelLabel}
          </Button>
        )}
      </div>
      <Progress
        value={determinate ? percent : null}
        aria-label={label}
        aria-valuetext={copy}
        className="mt-2 h-1 bg-line"
      />
    </div>
  );
}
