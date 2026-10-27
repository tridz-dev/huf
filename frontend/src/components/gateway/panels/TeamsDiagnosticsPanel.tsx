import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { AlertTriangle, CheckCircle2, Copy, Info, Loader2, RefreshCw, XCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import {
  diagnoseTeams,
  errorText,
  findCheck,
  getTeamsSupportBundle,
  type TeamsCheck,
  type TeamsCheckStatus,
  type TeamsDiagnosis,
} from '@/services/gateways/teamsApi';
import { registerProviderPanel, type ProviderPanelProps } from './index';

const STATUS_STYLE: Record<TeamsCheckStatus, { icon: typeof CheckCircle2; text: string; chip: string; label: string }> = {
  pass: {
    icon: CheckCircle2,
    text: 'text-green-600',
    chip: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
    label: 'OK',
  },
  warn: {
    icon: AlertTriangle,
    text: 'text-amber-600',
    chip: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
    label: 'Needs attention',
  },
  fail: {
    icon: XCircle,
    text: 'text-destructive',
    chip: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
    label: 'Problem',
  },
  info: { icon: Info, text: 'text-muted-foreground', chip: 'bg-muted text-muted-foreground', label: 'Note' },
};

const CHIPS: { label: string; checkId: string }[] = [
  { label: 'Credentials', checkId: 'credentials_present' },
  { label: 'Sign-in', checkId: 'token_acquisition' },
  { label: 'Messaging address', checkId: 'messaging_endpoint' },
  { label: 'Organisations', checkId: 'allowed_tenants' },
  { label: 'Last message in', checkId: 'last_inbound' },
  { label: 'Installs', checkId: 'conversation_references' },
  { label: 'Linked people', checkId: 'linked_users' },
  { label: 'Outgoing messages', checkId: 'outbox' },
];

export function TeamsStatusChips({ diagnosis }: { diagnosis: TeamsDiagnosis | null }) {
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Teams status">
      {CHIPS.map(({ label, checkId }) => {
        const check = findCheck(diagnosis, checkId);
        const style = check ? STATUS_STYLE[check.status] : null;
        return (
          <li key={checkId}>
            <Badge
              variant="secondary"
              className={cn('border-transparent', style ? style.chip : 'bg-muted text-muted-foreground')}
            >
              {label}: {style ? style.label : 'Not checked'}
            </Badge>
          </li>
        );
      })}
    </ul>
  );
}

export function TeamsCheckRow({ check }: { check: TeamsCheck }) {
  const style = STATUS_STYLE[check.status] ?? STATUS_STYLE.info;
  const Icon = style.icon;
  return (
    <li className="flex gap-2 text-sm">
      <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', style.text)} aria-hidden="true" />
      <div className="min-w-0 space-y-0.5">
        <p className="font-medium">
          {check.title} <span className="sr-only">{style.label}</span>
        </p>
        {check.detail && <p className="break-words text-muted-foreground">{check.detail}</p>}
        {check.status !== 'pass' && check.how_to_fix && <p>{check.how_to_fix}</p>}
      </div>
    </li>
  );
}

export function TeamsDiagnosticsPanel({ gateway }: ProviderPanelProps) {
  const [diagnosis, setDiagnosis] = useState<TeamsDiagnosis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copying, setCopying] = useState(false);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDiagnosis(await diagnoseTeams(gateway.name));
    } catch (e) {
      setError(errorText(e, 'Could not check the Teams connection'));
    } finally {
      setLoading(false);
    }
  }, [gateway.name]);

  useEffect(() => {
    void run();
  }, [run]);

  const copyBundle = useCallback(async () => {
    setCopying(true);
    try {
      const bundle = await getTeamsSupportBundle(gateway.name);
      await navigator.clipboard.writeText(JSON.stringify(bundle, null, 2));
      toast.success('Support details copied. Secrets and message content are not included.');
    } catch (e) {
      toast.error(errorText(e, 'Could not copy the support details'));
    } finally {
      setCopying(false);
    }
  }, [gateway.name]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" onClick={run} disabled={loading}>
          {loading ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
          {error ? 'Retry' : 'Run checks again'}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={copyBundle} disabled={copying}>
          {copying ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Copy className="mr-1 h-3.5 w-3.5" />}
          Copy support bundle
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading && !diagnosis && (
        <div className="space-y-2" aria-busy="true">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-5 w-3/4" />
        </div>
      )}

      {diagnosis && (
        <>
          <TeamsStatusChips diagnosis={diagnosis} />
          {diagnosis.checks.length === 0 ? (
            <p className="text-sm text-muted-foreground">No checks were returned.</p>
          ) : (
            <ul className="space-y-3" aria-label="Connection checks">
              {diagnosis.checks.map((check) => (
                <TeamsCheckRow key={check.id} check={check} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

registerProviderPanel('Microsoft Teams', {
  id: 'teams-diagnostics',
  title: 'Teams diagnostics',
  component: TeamsDiagnosticsPanel,
});
