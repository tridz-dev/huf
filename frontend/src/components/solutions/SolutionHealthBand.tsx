import { Link } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { SolutionOverview } from '@/types/solutions';

interface SolutionHealthBandProps {
  overview: SolutionOverview;
  /** Titles of other solutions, keyed by name, so the blame link reads well. */
  solutionLabels?: Record<string, string>;
  checking?: boolean;
  onCheck: () => void;
}

/** Health summary at the top of the Overview tab. Never claims a cause; blame is "most sends". */
export function SolutionHealthBand({ overview, solutionLabels = {}, checking = false, onCheck }: SolutionHealthBandProps) {
  const { health } = overview;
  const ok = health.state === 'ok';
  const number = overview.runs_on.find((r) => r.gateway === health.gateway);
  const numberText = number ? [number.label, number.phone].filter(Boolean).join(' ') : health.gateway;
  const blame = health.blame;
  const blameTitle = blame ? (blame.solution === overview.name ? overview.title : (solutionLabels[blame.solution] ?? blame.solution)) : '';

  return (
    <div
      role="status"
      data-state={health.state}
      className={cn(
        'flex flex-wrap items-start justify-between gap-3 rounded-lg border px-4 py-3 text-sm',
        ok ? 'border-line bg-panel text-ink' : health.state === 'bad' ? 'border-destructive/40 bg-destructive/5 text-ink' : 'border-amber-500/40 bg-amber-500/5 text-ink',
      )}
    >
      <div className="flex min-w-0 items-start gap-2">
        {ok ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
        ) : (
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden />
        )}
        <div className="space-y-1">
          {ok ? (
            <p>Working: {overview.title} is routing and replying normally.</p>
          ) : (
            <>
              <p>
                {health.state === 'bad' ? 'Problem' : 'Warning'} on {numberText}.
                {health.quality ? ` Quality rating: ${health.quality}.` : ''}
              </p>
              {blame ? (
                <p className="text-steel">
                  Most of today&apos;s sends came from{' '}
                  <Link to={`/solutions/${encodeURIComponent(blame.solution)}`} className="font-medium text-ink underline">
                    {blameTitle}
                  </Link>{' '}
                  ({Math.round(blame.share_pct)}% of sends in the last 24 hours).
                </p>
              ) : null}
            </>
          )}
        </div>
      </div>
      <Button variant="outline" size="sm" onClick={onCheck} disabled={checking}>
        {checking ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" aria-hidden /> : null}
        Check now
      </Button>
    </div>
  );
}
