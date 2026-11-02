import { AlertTriangle, CheckCircle2, CircleDot, Clock, Loader2, XCircle, type LucideIcon } from 'lucide-react';
import { Badge, type BadgeProps } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { FlowStatus } from '@/types/flow.types';

/**
 * The one status set for flows and runs (UX_DESIGN_DECISIONS (i)). Words are always sentence case, never
 * upper case. Internal status values (Draft / Active / Published / Success ...) never reach the screen: map
 * them to a kind with `flowStatusKind` and show the label from here.
 */
export type StatusKind =
  | 'draft'
  | 'expired'
  | 'live'
  | 'has_problems'
  | 'archived'
  | 'queued'
  | 'running'
  | 'waiting_approval'
  | 'waiting_review'
  | 'finished'
  | 'failed'
  | 'stuck'
  | 'approved'
  | 'rejected'
  | 'timed_out';

interface StatusSpec {
  label: string;
  variant: NonNullable<BadgeProps['variant']>;
  icon: LucideIcon | null;
  spin?: boolean;
}

export const STATUS_SPECS: Record<StatusKind, StatusSpec> = {
  draft: { label: 'Draft', variant: 'pill-neutral', icon: null },
  live: { label: 'Live', variant: 'pill-success', icon: CircleDot },
  has_problems: { label: 'Has problems', variant: 'pill-warning', icon: AlertTriangle },
  archived: { label: 'Archived', variant: 'pill-neutral', icon: null },
  queued: { label: 'Queued', variant: 'pill-neutral', icon: Clock },
  running: { label: 'Running', variant: 'pill-info', icon: Loader2, spin: true },
  waiting_approval: { label: 'Waiting for approval', variant: 'pill-warning', icon: Clock },
  waiting_review: { label: 'Waiting for code review', variant: 'pill-warning', icon: Clock },
  finished: { label: 'Finished', variant: 'pill-success', icon: CheckCircle2 },
  failed: { label: 'Failed', variant: 'pill-danger', icon: XCircle },
  stuck: { label: 'Stuck', variant: 'pill-warning', icon: AlertTriangle },
  approved: { label: 'Approved', variant: 'pill-success', icon: null },
  rejected: { label: 'Rejected', variant: 'pill-danger', icon: null },
  expired: { label: 'Expired', variant: 'pill-neutral', icon: Clock },
  timed_out: { label: 'Timed out', variant: 'pill-neutral', icon: null },
};

/** The word shown for a kind. */
export function statusLabel(kind: StatusKind): string {
  return STATUS_SPECS[kind].label;
}

/**
 * Flow lifecycle kind for the list card and the editor header. The stored status stays 'active' for a published
 * flow; people read "Live". A live flow that no longer passes its checks reads "Has problems". A draft with
 * unfinished steps is still just a "Draft": the editor's "N things to finish" says what is left.
 */
export function flowStatusKind(status: FlowStatus | undefined, problemCount = 0): StatusKind {
  if (status === 'active') return problemCount > 0 ? 'has_problems' : 'live';
  if (status === 'paused') return 'archived';
  if (status === 'error') return 'has_problems';
  return 'draft';
}

interface StatusPillProps {
  kind: StatusKind;
  className?: string;
  /** Icon-only below the `xl` breakpoint (tight headers) for kinds that have an icon; the word stays available to screen readers. */
  compact?: boolean;
  /** Overrides the default word (rare: keep to the shared vocabulary). */
  label?: string;
  title?: string;
  'data-testid'?: string;
}

export function StatusPill({ kind, className, compact, label, title, 'data-testid': testId }: StatusPillProps) {
  const spec = STATUS_SPECS[kind];
  const Icon = spec.icon;
  const text = label ?? spec.label;
  return (
    <Badge
      variant={spec.variant}
      className={cn('shrink-0 gap-1 whitespace-nowrap px-2 py-0.5', className)}
      title={title ?? text}
      data-testid={testId ?? `status-pill-${kind}`}
      data-status={kind}
    >
      {Icon && <Icon className={cn('h-3 w-3', spec.spin && 'animate-spin')} aria-hidden />}
      <span className={compact && Icon ? 'sr-only xl:not-sr-only' : undefined}>{text}</span>
    </Badge>
  );
}
