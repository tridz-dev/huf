import { useCallback, useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { listOrders, type OrderRow } from '@/services/channels/commerceApi';
import { OrderDrawer } from './OrderDrawer';

export function OrdersTab({ gw }: { gw: string }) {
  const [rows, setRows] = useState<OrderRow[] | null>(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await listOrders(gw);
    if (res.ok) { setRows(Array.isArray(res.data) ? res.data : []); setError(''); } else setError(res.error);
  }, [gw]);
  useEffect(() => { void load(); }, [load]);

  return (
    <div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {rows && rows.length === 0 && <p className="text-sm text-steel">No orders yet. Orders appear when a customer sends a cart.</p>}
      {rows && rows.length > 0 && (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-steel">
            <tr><th className="py-1">Order</th><th>Contact</th><th>Total</th><th>Status</th><th>Payment</th><th>Created</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} tabIndex={0} role="button" aria-label={`Open order ${r.name}`} className="cursor-pointer border-t border-line hover:bg-paper-deep"
                onClick={() => setOpen(r.name)} onKeyDown={(e) => { if (e.key === 'Enter') setOpen(r.name); }}>
                <td className="py-1.5 font-mono text-xs text-ink">{r.name}</td>
                <td className="text-ink-soft">{r.contact_handle}</td>
                <td className="text-ink">{r.currency} {r.total}</td>
                <td><Badge variant="chip" size="sm">{r.status}</Badge></td>
                <td className="text-ink-soft">{r.payment_status || '—'}</td>
                <td className="text-steel">{(r.creation ?? '').slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <OrderDrawer name={open} onClose={() => setOpen(null)} onChanged={() => void load()} />
    </div>
  );
}
