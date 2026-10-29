import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { IntegrationHealth } from '@/lib/integrations/health';
import { formatTimeAgo } from '@/utils/time';
import { IntegrationStatusPill } from './IntegrationStatusPill';

interface ConnectionStatusLineProps {
  health: IntegrationHealth;
  /** When the answer was given (a saved check). Empty for a check of values that were only typed. */
  checkedAt?: string;
  /** Answer came from values typed on the form and not saved yet. */
  unsaved?: boolean;
  testing: boolean;
  /** Says what to do with the credentials ("Add credentials", "Update credentials"); empty when nothing is needed. */
  fixLabel?: string;
  onFix?: () => void;
  /** Newer problem reported by a step after the last good check. */
  lastProblem?: string;
  onDismissProblem?: () => void;
}

/** The one place the page says whether this connection works: a pill, a sentence, and the next step. */
export function ConnectionStatusLine({
  health,
  checkedAt,
  unsaved,
  testing,
  fixLabel,
  onFix,
  lastProblem,
  onDismissProblem,
}: ConnectionStatusLineProps) {
  return (
    <div className="space-y-2" data-testid="integration-status-line">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        {testing ? (
          <span className="inline-flex items-center gap-2 text-sm text-steel" role="status">
            <Loader2 className="h-4 w-4 animate-spin" /> Checking the connection...
          </span>
        ) : (
          <>
            <IntegrationStatusPill health={health} />
            {(health.detail || checkedAt || unsaved) && (
              <p
                className="min-w-0 max-w-prose break-words text-sm text-foreground"
                role="status"
                data-testid="integration-test-result"
                data-status={health.kind}
              >
                {health.detail}
                {unsaved && <span className="text-steel"> Checked with the values you typed. Save to keep them.</span>}
                {checkedAt && <span className="text-steel"> Checked {formatTimeAgo(checkedAt).toLowerCase()}.</span>}
              </p>
            )}
            {fixLabel && onFix && (
              <Button type="button" size="sm" variant="outline" onClick={onFix} data-testid="integration-fix-credentials">
                {fixLabel}
              </Button>
            )}
          </>
        )}
      </div>
      {lastProblem && !testing && (
        <div
          className="flex flex-wrap items-start gap-x-3 gap-y-1 rounded-md border border-warning/40 bg-warning-tint px-3 py-2 text-sm"
          data-testid="integration-last-problem"
        >
          <p className="min-w-0 flex-1 break-words">
            <span className="font-medium">Problem since the last check: </span>
            {lastProblem}
          </p>
          {onDismissProblem && (
            <Button type="button" size="sm" variant="ghost" className="h-auto px-2 py-0.5" onClick={onDismissProblem}>
              Dismiss
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
