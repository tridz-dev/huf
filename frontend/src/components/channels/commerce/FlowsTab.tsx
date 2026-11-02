import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { listFlowResponses, listWaFlows, type FlowResponseRow, type FlowRow } from '@/services/channels/commerceApi';

export function FlowsTab({ gw }: { gw: string }) {
  const [flows, setFlows] = useState<FlowRow[] | null>(null);
  const [responses, setResponses] = useState<FlowResponseRow[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (refresh: number) => {
    setBusy(true);
    const [f, r] = await Promise.all([listWaFlows(gw, refresh), listFlowResponses(gw)]);
    setBusy(false);
    if (f.ok) { setFlows(Array.isArray(f.data) ? f.data : []); setError(''); } else setError(f.error);
    if (r.ok) setResponses(Array.isArray(r.data) ? r.data : []);
  }, [gw]);
  useEffect(() => { void load(0); }, [load]);

  return (
    <div className="flex flex-col gap-5">
      <section aria-label="Flows">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-ink">WhatsApp Flows</h2>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void load(1)}><RefreshCw className="mr-1 h-3 w-3" />Refresh</Button>
        </div>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {flows && flows.length === 0 && <p className="text-xs text-steel">No flows yet. Refresh to pull them from Meta.</p>}
        {flows && flows.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-steel"><tr><th className="py-1">Name</th><th>Status</th><th>Categories</th><th>Last synced</th></tr></thead>
            <tbody>
              {flows.map((f) => (
                <tr key={f.name} className="border-t border-line">
                  <td className="py-1.5 text-ink">{f.flow_name || f.flow_id}</td>
                  <td className="text-ink-soft">{f.status}</td>
                  <td className="text-ink-soft">{f.categories}</td>
                  <td className="text-steel">{(f.last_synced ?? '').slice(0, 16)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section aria-label="Recent flow responses">
        <h2 className="mb-2 text-sm font-medium text-ink">Recent responses</h2>
        {responses.length === 0 ? <p className="text-xs text-steel">No responses yet.</p> : (
          <ul className="divide-y divide-line text-sm">
            {responses.map((r) => (
              <li key={r.name} className="flex justify-between py-1.5">
                <span className="text-ink">{r.flow}</span>
                <span className="text-steel">{(r.received_at ?? '').slice(0, 16)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
