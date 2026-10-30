import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { updateGateway, type GatewayDoc } from '@/services/gatewayApi';
import { syncCatalogNow, type SyncResult } from '@/services/channels/commerceApi';
import type { EcosystemApp } from '@/services/channels/channelsApi';
import { ConnectionCard, CARDS } from '../connections/ConnectionCards';

export interface TabProps {
  gw: string;
  gateway: Record<string, unknown> | null;
  onSaved: () => void;
}

export function CatalogTab({ gw, gateway, onSaved, erpnext, isAdmin }: TabProps & { erpnext?: EcosystemApp; isAdmin: boolean }) {
  const [catalogId, setCatalogId] = useState(String(gateway?.catalog_id ?? ''));
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<SyncResult | null>(null);

  const save = async () => {
    setBusy(true);
    setError('');
    try {
      await updateGateway(gw, { catalog_id: catalogId.trim() } as unknown as Partial<GatewayDoc>);
      toast.success('Catalog ID saved');
      onSaved();
    } catch (e) {
      setError(getFrappeErrorMessage(e));
    }
    setBusy(false);
  };

  const sync = async () => {
    setSyncing(true);
    setError('');
    const res = await syncCatalogNow(gw);
    setSyncing(false);
    if (!res.ok) return setError(res.error);
    setResult(res.data);
  };

  const erpCard = CARDS.find((c) => c.key === 'erpnext')!;
  return (
    <div className="flex max-w-xl flex-col gap-4">
      <Field label="Catalog ID" hint="Your Meta Commerce catalog. ERPNext Items sync to it.">
        <div className="flex gap-2">
          <Input value={catalogId} onChange={(e) => setCatalogId(e.target.value)} aria-label="Catalog ID" />
          <Button size="sm" disabled={busy} onClick={() => void save()}>Save</Button>
        </div>
      </Field>
      {erpnext && !erpnext.installed ? (
        <ConnectionCard def={erpCard} app={erpnext} isAdmin={isAdmin} />
      ) : (
        <div className="flex flex-col gap-2">
          <div>
            <Button size="sm" variant="outline" disabled={syncing || !catalogId.trim()} onClick={() => void sync()}>
              {syncing && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}Sync from ERPNext now
            </Button>
          </div>
          {result && (
            <div role="status" aria-label="Sync result" className="rounded-sm border border-line p-3 text-sm text-ink">
              <p className={result.success ? 'text-success' : 'text-destructive'}>{result.success ? 'Catalog synced.' : result.error || 'Some items failed.'}</p>
              {result.items != null && (
                <dl className="mt-1 grid grid-cols-4 gap-2 text-xs text-steel">
                  <div><dt>Items</dt><dd className="text-ink">{result.items}</dd></div>
                  <div><dt>Synced</dt><dd className="text-ink">{result.synced ?? 0}</dd></div>
                  <div><dt>Failed</dt><dd className="text-ink">{result.failed ?? 0}</dd></div>
                  <div><dt>Skipped</dt><dd className="text-ink">{result.skipped ?? 0}</dd></div>
                </dl>
              )}
              {(result.errors ?? []).map((e, i) => <p key={i} className="mt-1 text-xs text-destructive">{e}</p>)}
            </div>
          )}
        </div>
      )}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
