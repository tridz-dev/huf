/**
 * AttentionBanner (DESIGN.md §6.10.6): "N things need you" in one line, with
 * one primary fix and an optional secondary "Show them". It counts; the rows
 * themselves carry the per-item reason. Never stack two banners: merge the
 * counts into one sentence. Hide it when the count is 0.
 */
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface AttentionBannerProps {
  /** Plain sentence, e.g. "3 documents could not be added." */
  message: string;
  count?: number;
  /** The one fix, e.g. "Retry all". */
  action?: { label: string; onClick: () => void; busy?: boolean };
  /** Usually "Show them": applies the matching filter. */
  secondary?: { label: string; onClick: () => void };
  className?: string;
}

export function AttentionBanner({ message, count, action, secondary, className }: AttentionBannerProps) {
  if (count === 0) return null;
  return (
    <div
      role="alert"
      data-testid="attention-banner"
      className={cn('flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line bg-warning-tint px-4 py-2.5 text-ui-text text-ink', className)}
    >
      <AlertTriangle aria-hidden="true" className="h-4 w-4 shrink-0 text-warning" />
      <span className="min-w-0">{message}</span>
      <span className="flex-1" />
      {secondary && (
        <Button type="button" variant="link" size="sm" onClick={secondary.onClick}>
          {secondary.label}
        </Button>
      )}
      {action && (
        <Button type="button" variant="outline" size="sm" disabled={action.busy} onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}
