import { Fragment, useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  canExplainEvent,
  diagnoseGatewayEvent,
  eventStatusLabel,
  eventStatusTone,
  failedCount,
  formatCost,
  formatTokens,
  getGatewayHealth,
  type DiagnosisCheck,
  type GatewayHealth,
  type StatusTone,
} from '@/services/gatewayHealthApi';
import type { GatewayProvider } from '@/services/gatewayApi';
import { formatTimeAgo } from '@/utils/time';
import { cn } from '@/lib/utils';
import { registerProviderPanel, type ProviderPanelProps } from './index';

const REFRESH_INTERVAL_MS = 30_000;

const TONE_CLASSES: Record<StatusTone, string> = {
  success: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  warning: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  danger: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  neutral: 'bg-muted text-muted-foreground',
};

function Chip({ tone, children }: { tone: StatusTone; children: React.ReactNode }) {
  return (
    <Badge variant="secondary" className={cn('border-transparent', TONE_CLASSES[tone])}>
      {children}
    </Badge>
  );
}

function Diagnosis({ eventName }: { eventName: string }) {
  const [checks, setChecks] = useState<DiagnosisCheck[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    diagnoseGatewayEvent(eventName)
      .then((result) => !cancelled && setChecks(result))
      .catch(() => !cancelled && setError('We could not check this message. Try again.'));
    return () => {
      cancelled = true;
    };
  }, [eventName]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!checks) return <Skeleton className="h-16 w-full" />;
  return (
    <ul className="space-y-2 text-sm">
      {checks.map((item) => (
        <li key={item.check} className="flex gap-2">
          <Chip tone={item.ok ? 'success' : 'danger'}>{item.ok ? 'OK' : 'Problem'}</Chip>
          <div>
            <p className="font-medium">{item.check}</p>
            <p className="text-muted-foreground">{item.plain_language_explanation}</p>
            {!item.ok && item.how_to_fix && <p>How to fix: {item.how_to_fix}</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function HealthPanel({ gateway }: ProviderPanelProps) {
  const [health, setHealth] = useState<GatewayHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [explaining, setExplaining] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setHealth(await getGatewayHealth(gateway.name));
      setError(null);
    } catch {
      setError('We could not load recent activity. Try again in a moment.');
    } finally {
      setLoading(false);
    }
  }, [gateway.name]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {health && (
            <>
              <Chip tone={health.status.enabled ? 'success' : 'neutral'}>
                {health.status.enabled ? 'On' : 'Off'}
              </Chip>
              <span className="text-sm text-muted-foreground">
                Last message: {formatTimeAgo(health.status.last_event_at)}
              </span>
            </>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          <RefreshCw className={cn('mr-2 h-4 w-4', loading && 'animate-spin')} />
          Refresh
        </Button>
      </div>

      {error && (
        <p role="status" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {loading && !health && <Skeleton className="h-32 w-full" />}

      {health && (
        <>
          {health.status.last_error && (
            <Alert variant="destructive">
              <AlertDescription>Last problem: {health.status.last_error}</AlertDescription>
            </Alert>
          )}

          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <p className="text-muted-foreground">Messages, last 24 hours</p>
              <p className="text-lg font-semibold">{health.counts['24h'].total}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Problems, last 24 hours</p>
              <p className="text-lg font-semibold">{failedCount(health.counts['24h'])}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Messages, last 7 days</p>
              <p className="text-lg font-semibold">{health.counts['7d'].total}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Usage, last 7 days</p>
              <p className="text-lg font-semibold">
                {formatCost(health.usage_7d.cost)}
                <span className="ml-1 text-xs font-normal text-muted-foreground">
                  {formatTokens(health.usage_7d.total_tokens)} tokens
                </span>
              </p>
            </div>
          </div>

          {health.recent_events.length === 0 ? (
            <p className="text-sm text-muted-foreground">No messages received yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Received</TableHead>
                  <TableHead>From</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Handled by</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {health.recent_events.map((event) => (
                  <Fragment key={event.name}>
                    <TableRow>
                      <TableCell>{formatTimeAgo(event.received_at)}</TableCell>
                      <TableCell>{event.sender || '-'}</TableCell>
                      <TableCell>
                        <Chip tone={eventStatusTone(event.status)}>{eventStatusLabel(event.status)}</Chip>
                        {event.error_message && (
                          <p className="mt-1 text-xs text-muted-foreground">{event.error_message}</p>
                        )}
                      </TableCell>
                      <TableCell>{event.target || '-'}</TableCell>
                      <TableCell>
                        {canExplainEvent(event.status) && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setExplaining(explaining === event.name ? null : event.name)}
                          >
                            Why didn&apos;t this run?
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                    {explaining === event.name && (
                      <TableRow>
                        <TableCell colSpan={5}>
                          <Diagnosis eventName={event.name} />
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          )}
        </>
      )}
    </div>
  );
}

const HEALTH_PROVIDERS: GatewayProvider[] = [
  'WhatsApp',
  'Messenger',
  'Instagram',
  'Telegram',
  'Slack',
  'Email',
  'Google Chat',
  'Microsoft Teams',
];

for (const provider of HEALTH_PROVIDERS) {
  registerProviderPanel(provider, { id: 'health', title: 'Activity', component: HealthPanel });
}
