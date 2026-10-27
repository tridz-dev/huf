import { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { generateTeamsAppManifest } from './teamsApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { base64ToBlob, mapManifestError } from './teamsOnboarding';

export function TeamsManifestDownload({ gatewayName }: { gatewayName: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = async () => {
    setBusy(true);
    setError(null);
    try {
      const pkg = await generateTeamsAppManifest(gatewayName);
      const url = URL.createObjectURL(base64ToBlob(pkg.content_base64));
      const a = document.createElement('a');
      a.href = url;
      a.download = pkg.filename || 'teams-app.zip';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success('Teams app package downloaded');
    } catch (e) {
      const msg = mapManifestError(getFrappeErrorMessage(e));
      setError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button type="button" variant="outline" size="sm" onClick={download} disabled={busy}>
        {busy ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Download className="mr-1.5 h-3.5 w-3.5" />}
        Download Teams app package
      </Button>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
