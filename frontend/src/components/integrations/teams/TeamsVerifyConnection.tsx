import { useState } from 'react';
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { verifyTeamsConnection } from './teamsApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { VerifyResult } from './teamsOnboarding';

export function TeamsVerifyConnection({ gatewayName }: { gatewayName: string }) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);

  const run = async () => {
    setRunning(true);
    try {
      const res = await verifyTeamsConnection(gatewayName);
      setResult(res);
      if (res.ok) toast.success(res.message || 'Teams connection verified');
      else toast.error(res.message || 'Teams connection check failed');
    } catch (e) {
      const message = getFrappeErrorMessage(e) || 'Failed to verify the Teams connection';
      setResult({ ok: false, steps: [], message });
      toast.error(message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="outline" size="sm" onClick={run} disabled={running}>
          {running && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
          {running ? 'Verifying...' : 'Verify connection'}
        </Button>
        {result && <Badge variant={result.ok ? 'success' : 'destructive'}>{result.ok ? 'Verified' : 'Failed'}</Badge>}
      </div>
      {result && result.message && <p className="text-xs text-muted-foreground">{result.message}</p>}
      {result && result.steps.length > 0 && (
        <ul className="space-y-1" aria-label="Connection checks">
          {result.steps.map((s) => (
            <li key={s.id} className="flex items-start gap-2 text-xs">
              {s.ok ? (
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" aria-label="passed" />
              ) : (
                <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" aria-label="failed" />
              )}
              <span>
                {s.label}
                {s.detail && <span className="block text-muted-foreground">{s.detail}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
