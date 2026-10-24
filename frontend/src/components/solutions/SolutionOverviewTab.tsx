import { useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { goLive, pauseSolution, resumeSolution } from '@/services/solutionsApi';
import type { SolutionOverview } from '@/types/solutions';
import { SolutionHealthBand } from './SolutionHealthBand';
import { labels, purposeLabel } from './labels';
import { SolutionAnsweredByPicker } from './SolutionAnsweredByPicker';

interface SolutionOverviewTabProps {
  overview: SolutionOverview;
  solutionLabels?: Record<string, string>;
  checking?: boolean;
  onCheck: () => void;
  /** Called after pause / resume / go live so the page refetches. */
  onChanged: () => void;
  onManageEntryPoints: () => void;
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-md border border-line p-3">
      <div className="text-xl font-semibold text-ink">{value}</div>
      <div className="text-xs text-steel">{label}</div>
    </div>
  );
}

function CardTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-3 text-sm font-semibold text-ink">{children}</h3>;
}

export function targetPath(type: 'Agent' | 'Flow', name: string): string {
  return type === 'Flow' ? `/flows/${encodeURIComponent(name)}` : `/agents/${encodeURIComponent(name)}`;
}

export function SolutionOverviewTab({ overview, solutionLabels, checking, onCheck, onChanged, onManageEntryPoints }: SolutionOverviewTabProps) {
  const [busy, setBusy] = useState(false);
  const [confirmLive, setConfirmLive] = useState(false);
  const [changing, setChanging] = useState(false);
  const live = overview.status === 'Live';
  const { reach, cost, primary } = overview;
  const ceiling = cost.ceiling;
  const usedPct = ceiling ? Math.min(100, Math.round((cost.sends_24h / ceiling) * 100)) : null;
  // cap_share is on a 0-100 scale (same as usage_pct) and null when there is nothing to share.
  const sharePct = Math.round(cost.cap_share ?? 0);

  const run = async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true);
    try {
      await fn();
      toast.success(done);
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setBusy(false);
      setConfirmLive(false);
    }
  };

  return (
    <div className="space-y-4">
      <SolutionHealthBand overview={overview} solutionLabels={solutionLabels} checking={checking} onCheck={onCheck} />

      <Card className="space-y-3 p-4">
        {overview.description ? <p className="text-sm text-ink">{overview.description}</p> : null}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-steel">{labels.purpose}</span>
            <Badge variant="outline">{purposeLabel(overview.purpose)}</Badge>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-steel">{labels.runsOn}</span>
            {overview.runs_on.length === 0 ? <span>-</span> : null}
            {overview.runs_on.map((r) => (
              <Badge key={r.gateway} variant="outline">{[r.label, r.phone].filter(Boolean).join(' ')}</Badge>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={live ? 'default' : 'secondary'}>{live ? 'Live' : 'Paused'}</Badge>
            {overview.test_mode ? <Badge variant="outline">Test mode</Badge> : null}
            {overview.shared ? <Badge variant="secondary">Shared</Badge> : null}
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <CardTitle>Reach</CardTitle>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-steel">Number</dt><dd>{overview.runs_on.map((r) => r.phone || r.label).join(', ') || '-'}</dd></div>
            <div className="flex justify-between"><dt className="text-steel">Entry points</dt><dd>{overview.entry_count}</dd></div>
            <div className="flex justify-between"><dt className="text-steel">Shared</dt><dd>{overview.shared ? 'Shared with other solutions' : 'Not shared'}</dd></div>
          </dl>
          <Button variant="outline" size="sm" className="mt-3" onClick={onManageEntryPoints}>Manage entry points</Button>
        </Card>

        <Card className="p-4">
          <CardTitle>Activity</CardTitle>
          <div className="grid grid-cols-2 gap-2">
            <Stat label="People this week" value={reach.contacts_7d} />
            <Stat label="New this week" value={reach.new_7d} />
            <Stat label="Chats this week" value={overview.chats_7d} />
            <Stat label="Recent events" value={overview.activity.length} />
          </div>
          {overview.activity.length > 0 ? (
            <ul className="mt-3 space-y-1 text-xs text-steel">
              {overview.activity.slice(0, 5).map((a, i) => (
                <li key={`${a.ts}-${i}`}>{a.text}</li>
              ))}
            </ul>
          ) : null}
        </Card>

        <Card className="p-4">
          <CardTitle>Cost and limits</CardTitle>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-steel">Messages sent, last 24 hours</dt><dd>{cost.sends_24h}</dd></div>
            <div className="flex justify-between"><dt className="text-steel">Share of the number&apos;s sends</dt><dd>{sharePct}%</dd></div>
            <div className="flex justify-between">
              <dt className="text-steel">Number limit per day</dt>
              <dd>{ceiling === null ? 'No limit set' : ceiling}</dd>
            </div>
          </dl>
          {ceiling !== null && usedPct !== null ? (
            <div className="mt-3">
              <div
                role="meter"
                aria-label="Daily limit used"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={usedPct}
                className="h-2 overflow-hidden rounded-full bg-line"
              >
                <div className="h-full bg-ink" style={{ width: `${usedPct}%` }} />
              </div>
              <div className="mt-1 text-xs text-steel">{usedPct}% of the daily limit used</div>
            </div>
          ) : null}
        </Card>

        <Card className={primary ? 'p-4' : 'border-ink p-4 lg:col-span-2'}>
          <CardTitle>{primary ? (primary.type === 'Flow' ? 'Flow' : 'Agent') : 'Choose what answers'}</CardTitle>
          {primary && !changing ? (
            <div className="flex flex-wrap items-center gap-3">
              <Link to={targetPath(primary.type, primary.name)} className="text-sm font-medium text-ink underline">
                {primary.label || primary.name}
              </Link>
              <Button variant="outline" size="sm" onClick={() => setChanging(true)}>Change</Button>
            </div>
          ) : (
            <div className="space-y-2">
              {!primary ? (
                <p className="text-sm text-steel">
                  No agent or flow answers yet, so this {labels.solutionLower} stays paused. Choose one to continue.
                </p>
              ) : null}
              <SolutionAnsweredByPicker
                solution={overview.name}
                current={primary}
                onSaved={() => { setChanging(false); onChanged(); }}
                onCancel={primary ? () => setChanging(false) : undefined}
              />
            </div>
          )}
          {primary ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {overview.test_mode ? (
                <Button size="sm" disabled={busy} onClick={() => setConfirmLive(true)}>Go live</Button>
              ) : live ? (
                <Button variant="outline" size="sm" disabled={busy} onClick={() => run(() => pauseSolution(overview.name), `${overview.title} paused.`)}>Pause</Button>
              ) : (
                <Button size="sm" disabled={busy} onClick={() => run(() => resumeSolution(overview.name), `${overview.title} resumed.`)}>Resume</Button>
              )}
            </div>
          ) : null}
        </Card>
      </div>

      <AlertDialog open={confirmLive} onOpenChange={setConfirmLive}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Go live with {overview.title}?</AlertDialogTitle>
            <AlertDialogDescription>
              Go live clears test mode. Real customer messages will start routing to this {labels.solutionLower}.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Not yet</AlertDialogCancel>
            <AlertDialogAction onClick={(e) => { e.preventDefault(); void run(() => goLive(overview.name), `${overview.title} is live.`); }}>
              Go live
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
