import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { getRateCard, saveRateCard, type RateRow } from '@/services/analyticsApi';

const CATEGORIES = ['marketing', 'utility', 'authentication', 'service'];

export function RateCardEditor({ onSaved }: { onSaved?: () => void }) {
  const [currency, setCurrency] = useState('');
  const [rows, setRows] = useState<RateRow[]>([]);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    void getRateCard().then((r) => {
      if (r.ok) {
        setCurrency(r.data.currency);
        setRows(r.data.rows);
      } else setMsg(r.error);
    });
  }, []);

  const patch = (i: number, p: Partial<RateRow>) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...p } : r)));

  const save = async () => {
    const res = await saveRateCard(currency, rows);
    if (res.ok) {
      setMsg('Saved');
      onSaved?.();
    } else setMsg(res.error);
  };

  return (
    <div className="space-y-3" aria-label="Rate card editor">
      <p className="text-xs text-steel">
        Enter rates from Meta&apos;s official rate card for your billing currency. Huf does not ship Meta prices.
      </p>
      <label className="flex items-center gap-2 text-sm text-ink">
        Currency
        <Input aria-label="Currency" className="w-24" value={currency} onChange={(e) => setCurrency(e.target.value)} />
      </label>
      {rows.map((r, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2">
          <Input aria-label={`Market ${i + 1}`} className="w-24" placeholder="IN" value={r.market} onChange={(e) => patch(i, { market: e.target.value })} />
          <select
            aria-label={`Category ${i + 1}`}
            className="rounded-md border border-line bg-panel px-2 py-1.5 text-sm text-ink"
            value={r.category}
            onChange={(e) => patch(i, { category: e.target.value })}
          >
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <Input aria-label={`Rate ${i + 1}`} className="w-28" inputMode="decimal" value={r.rate ?? ''} onChange={(e) => patch(i, { rate: e.target.value === '' ? null : Number(e.target.value) })} />
          <Input aria-label={`Effective from ${i + 1}`} className="w-40" type="date" value={r.effective_from ?? ''} onChange={(e) => patch(i, { effective_from: e.target.value || null })} />
          <Button size="sm" variant="ghost" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}>Remove</Button>
        </div>
      ))}
      <div className="flex items-center gap-2">
        <Button size="sm" variant="secondary" onClick={() => setRows((rs) => [...rs, { market: '', category: 'marketing', rate: null }])}>Add rate</Button>
        <Button size="sm" onClick={() => void save()}>Save rate card</Button>
        {msg && <span role="status" className="text-xs text-steel">{msg}</span>}
      </div>
    </div>
  );
}
