import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { BadgeProps } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  decideExternalApproval,
  listPendingExternalApprovals,
} from '@/services/externalAgentsApi';
import type { ExternalApproval } from '@/types/externalAgents.types';
import { formatAbsoluteTime, parseServerDate } from '@/lib/serverTime';

const POLL_INTERVAL_MS = 10000;
const MAX_ARG_ENTRIES = 12;
const MAX_ARG_VALUE_LENGTH = 200;

type Decision = 'approve' | 'decline';

const KIND_BADGES: Record<
  ExternalApproval['action_class'],
  { label: string; variant: NonNullable<BadgeProps['variant']> }
> = {
  read: { label: 'Read', variant: 'pill-neutral' },
  write: { label: 'Change', variant: 'pill-warning' },
  communicate: { label: 'Message', variant: 'pill-info' },
};

function sentenceCase(text: string): string {
  const spaced = text.replace(/_/g, ' ').trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function formatArgValue(value: unknown): string {
  let text: string;
  if (value === null || value === undefined) {
    text = '—';
  } else if (typeof value === 'string') {
    text = value;
  } else if (typeof value === 'object') {
    text = JSON.stringify(value) ?? String(value);
  } else {
    text = String(value);
  }
  return text.length > MAX_ARG_VALUE_LENGTH
    ? `${text.slice(0, MAX_ARG_VALUE_LENGTH)}…`
    : text;
}

function formatExpiry(expiresOn: string, now: number): string {
  const expires = parseServerDate(expiresOn);
  if (!expires) return 'Expiry unknown';

  const diffMs = expires.getTime() - now;
  if (diffMs <= 0) return 'Expired';

  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return 'Expires in under a minute';
  if (minutes < 60) return `Expires in ${minutes} min`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `Expires in ${hours} hr`;

  return `Expires ${formatAbsoluteTime(expires)}`;
}

interface ApprovalCardProps {
  approval: ExternalApproval;
  now: number;
  decision: Decision | undefined;
  onDecide: (approval: ExternalApproval, approve: boolean) => void;
}

function ApprovalCard({ approval, now, decision, onDecide }: ApprovalCardProps) {
  const kind = KIND_BADGES[approval.action_class] ?? KIND_BADGES.read;
  const entries = Object.entries(approval.args ?? {});
  const shownEntries = entries.slice(0, MAX_ARG_ENTRIES);
  const hiddenCount = entries.length - shownEntries.length;
  const isBusy = decision !== undefined;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base">Approval needed</CardTitle>
          <Badge variant={kind.variant}>{kind.label}</Badge>
        </div>
        <CardDescription>
          {sentenceCase(approval.tool_name)} · {formatExpiry(approval.expires_on, now)}
        </CardDescription>
      </CardHeader>

      <CardContent>
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">No details provided.</p>
        ) : (
          <dl className="space-y-2">
            {shownEntries.map(([key, value]) => (
              <div
                key={key}
                className="flex flex-col gap-0.5 text-sm sm:flex-row sm:gap-3"
              >
                <dt className="shrink-0 text-muted-foreground sm:w-40">
                  {sentenceCase(key)}
                </dt>
                <dd className="min-w-0 break-words">{formatArgValue(value)}</dd>
              </div>
            ))}
            {hiddenCount > 0 && (
              <p className="text-sm text-muted-foreground">+{hiddenCount} more</p>
            )}
          </dl>
        )}
      </CardContent>

      <CardFooter className="justify-end gap-2">
        <Button
          variant="outline"
          disabled={isBusy}
          onClick={() => onDecide(approval, false)}
        >
          Decline
        </Button>
        <Button disabled={isBusy} onClick={() => onDecide(approval, true)}>
          {decision === 'approve' && <Loader2 className="animate-spin" />}
          Approve
        </Button>
      </CardFooter>
    </Card>
  );
}

export function ApprovalsSection() {
  const [approvals, setApprovals] = useState<ExternalApproval[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});

  const load = useCallback(async () => {
    try {
      const rows = await listPendingExternalApprovals();
      setApprovals(rows);
    } catch {
      // Keep the last known list; the next poll tries again.
    } finally {
      setLoaded(true);
      setNow(Date.now());
    }
  }, []);

  useEffect(() => {
    void load();
    const intervalId = window.setInterval(() => {
      setNow(Date.now());
      void load();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [load]);

  const handleDecide = useCallback(
    async (approval: ExternalApproval, approve: boolean) => {
      setDecisions((prev) => ({ ...prev, [approval.name]: approve ? 'approve' : 'decline' }));
      try {
        await decideExternalApproval(approval, approve);
        toast.success(approve ? 'Request approved' : 'Request declined');
      } catch {
        toast.error(
          approve
            ? 'Could not approve this request. Please try again.'
            : 'Could not decline this request. Please try again.'
        );
      } finally {
        setDecisions((prev) => {
          const next = { ...prev };
          delete next[approval.name];
          return next;
        });
        await load();
      }
    },
    [load]
  );

  if (!loaded) return null;

  if (approvals.length === 0) {
    return <p className="text-sm text-muted-foreground">Nothing waiting for your approval.</p>;
  }

  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold">Approvals</h2>
      <div className="grid gap-4">
        {approvals.map((approval) => (
          <ApprovalCard
            key={approval.name}
            approval={approval}
            now={now}
            decision={decisions[approval.name]}
            onDecide={handleDecide}
          />
        ))}
      </div>
    </section>
  );
}
