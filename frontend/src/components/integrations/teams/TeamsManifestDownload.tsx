import { useEffect, useRef, useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { generateTeamsAppManifest } from './teamsApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { TEAMS_FORBIDDEN_NOTICE, TEAMS_PACKAGE_DECODE_ERROR, isForbiddenError, TEAMS_REVOKE_DELAY_MS, base64ToBlob, mapManifestError } from './teamsOnboarding';

export function TeamsManifestDownload({ gatewayName, disabledReason }: { gatewayName: string; disabledReason?: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inFlight = useRef(false);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const download = async () => {
    if (inFlight.current || disabledReason) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const pkg = await generateTeamsAppManifest(gatewayName);
      let blob: Blob;
      try {
        blob = base64ToBlob(pkg.content_base64);
      } catch {
        throw new Error(TEAMS_PACKAGE_DECODE_ERROR);
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = pkg.filename || 'teams-app.zip';
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Safari may start the download asynchronously; revoke later.
      timers.current.push(setTimeout(() => URL.revokeObjectURL(url), TEAMS_REVOKE_DELAY_MS));
      toast.success('Teams app package downloaded');
    } catch (e) {
      const msg = isForbiddenError(e) ? TEAMS_FORBIDDEN_NOTICE : mapManifestError(getFrappeErrorMessage(e));
      setError(msg);
      toast.error(msg);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button type="button" variant="outline" size="sm" onClick={download} disabled={busy || Boolean(disabledReason)}>
        {busy ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Download className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />}
        Download Teams app package
      </Button>
      {disabledReason && <p className="text-xs text-muted-foreground">{disabledReason}</p>}
      {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
    </div>
  );
}
