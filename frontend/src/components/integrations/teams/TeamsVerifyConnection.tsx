import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { verifyTeamsConnection } from './teamsApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { TEAMS_RATE_LIMIT_NOTICE, TEAMS_VERIFY_COOLDOWN_MS, isRateLimitError, type VerifyResult } from './teamsOnboarding';

export function TeamsVerifyConnection({ gatewayName }: { gatewayName: string }) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);

  const [cooling, setCooling] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const startCooldown = () => {
    setCooling(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCooling(false), TEAMS_VERIFY_COOLDOWN_MS);
  };

  const run = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setNotice(null);
    setRunning(true);
    try {
      const res = await verifyTeamsConnection(gatewayName);
      setResult(res);
      if (res.ok) toast.success(res.message || 'Teams connection verified');
      else toast.error(res.message || 'Teams connection check failed');
    } catch (e) {
      if (isRateLimitError(e)) {
        // Keep the previous result; the server throttles to one run per few seconds.
        setNotice(TEAMS_RATE_LIMIT_NOTICE);
        toast.info(TEAMS_RATE_LIMIT_NOTICE);
        return;
      }
      const message = getFrappeErrorMessage(e) || 'Failed to verify the Teams connection';
      setResult({ ok: false, steps: [], message });
      toast.error(message);
    } finally {
      inFlight.current = false;
      setRunning(false);
      startCooldown();
    }
  };

  return (
    <div className="space-y-2">
      <div aria-live="polite" className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="outline" size="sm" onClick={run} disabled={running || cooling}>
          {running && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
          {running ? 'Verifying...' : 'Verify connection'}
        </Button>
        {result && <Badge variant={result.ok ? 'success' : 'destructive'}>{result.ok ? 'Verified' : 'Failed'}</Badge>}
      </div>
      {notice && <p className="text-xs text-muted-foreground" role="status">{notice}</p>}
      {result && result.message && <p className="text-xs text-muted-foreground">{result.message}</p>}
      {result && result.steps.length > 0 && (
        <ul className="space-y-1" aria-label="Connection checks">
          {result.steps.map((s) => (
            <li key={s.id} className="flex items-start gap-2 text-xs">
              {s.ok ? (
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-good" role="img" aria-label="passed" />
              ) : (
                <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" role="img" aria-label="failed" />
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
    </div>
  );
}
