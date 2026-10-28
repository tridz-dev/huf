import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { errorText } from '@/services/whatsappApi';
import { getBroadcastLimits, updateBroadcastLimits, type BroadcastLimit, type LimitGroup, type LimitValue } from './limitsApi';

const GROUPS: { id: LimitGroup; title: string; blurb: string }[] = [
  { id: 'meta', title: 'Set by Meta', blurb: 'WhatsApp enforces these. Huf shows them so you know why a message may not go out.' },
  { id: 'recipients', title: 'Recipients and uploads', blurb: 'How many people and rows one broadcast or upload can include.' },
  { id: 'speed', title: 'Sending speed', blurb: 'How fast messages go out.' },
  { id: 'safety', title: 'Safety checks', blurb: 'Protections Huf adds. Turn them off only if you understand the risk.' },
  { id: 'quality', title: 'Number quality', blurb: 'What Huf does when your number quality drops or you pass your daily budget.' },
  { id: 'confirmation', title: 'Confirmation steps', blurb: 'Extra confirmations before a broadcast starts.' },
  { id: 'api', title: 'Request rate limits', blurb: 'How often each action can be called.' },
];

const BADGE: Record<BroadcastLimit['kind'], { text: string; variant: 'outline' | 'secondary' | 'default' }> = {
  meta: { text: 'Set by Meta', variant: 'outline' },
  setting: { text: 'Huf setting', variant: 'secondary' },
  safety: { text: 'Safety', variant: 'default' },
  internal: { text: 'Internal', variant: 'outline' },
};

const show = (v: LimitValue, unit?: string | null) => {
  if (v === null || v === undefined || v === '') return 'No limit';
  if (typeof v === 'boolean') return v ? 'On' : 'Off';
  return unit ? `${v} ${unit}` : String(v);
};

type Draft = Record<string, LimitValue | undefined>;

export function BroadcastLimits() {
  const [limits, setLimits] = useState<BroadcastLimit[] | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await getBroadcastLimits();
    if (res.success) { setLimits(res.limits); setDraft({}); setErr(''); }
    else { setLimits([]); setErr(errorText(res)); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const dirty = Object.keys(draft);
  const current = (l: BroadcastLimit): LimitValue => (l.key in draft ? (draft[l.key] as LimitValue) : l.value);
  const setVal = (l: BroadcastLimit, v: LimitValue) =>
    setDraft((d) => {
      const n = { ...d };
      if (v === l.value) delete n[l.key]; else n[l.key] = v;
      return n;
    });

  const numberError = (l: BroadcastLimit, v: LimitValue): string | undefined => {
    if (v === null || v === '' || typeof v === 'boolean') return undefined;
    const n = Number(v);
    if (!Number.isFinite(n)) return 'Enter a number';
    if (l.min != null && n < l.min) return `Must be at least ${l.min}`;
    if (l.max != null && n > l.max) return `Must be at most ${l.max}`;
    return undefined;
  };
  const invalid = useMemo(() => (limits ?? []).some((l) => l.key in draft && numberError(l, draft[l.key] as LimitValue)), [limits, draft]);

  const save = async () => {
    setBusy(true);
    const values: Record<string, LimitValue> = {};
    for (const [k, v] of Object.entries(draft)) values[k] = v === '' || v === undefined ? null : v as LimitValue;
    const res = await updateBroadcastLimits(values);
    setBusy(false);
    if (res.success) { setLimits(res.limits); setDraft({}); setErr(''); toast.success('Broadcast limits saved'); }
    else setErr(errorText(res));
  };

  const control = (l: BroadcastLimit) => {
    const v = current(l);
    if (typeof l.default === 'boolean' || typeof l.value === 'boolean') {
      return (
        <Switch aria-label={l.label} checked={v === true} onCheckedChange={(c) => setVal(l, c)} />
      );
    }
    const error = numberError(l, v);
    return (
      <Field label={l.label} id={`lim-${l.key}`} error={error} size="sm">
        {(p) => (
          <Input
            {...p}
            inputMode="decimal"
            value={v === null || v === undefined ? '' : String(v)}
            placeholder={l.default === null ? 'No limit' : String(l.default)}
            onChange={(e) => {
              const t = e.target.value.trim();
              setVal(l, t === '' ? null : /^-?\d+(\.\d+)?$/.test(t) ? Number(t) : t);
            }}
          />
        )}
      </Field>
    );
  };

  if (limits === null) return <p className="text-sm text-steel">Loading broadcast limits...</p>;

  return (
    <section aria-label="Broadcast limits" className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-ink">Broadcast limits</h3>
        <p className="text-sm text-steel">Every rule that affects a broadcast, and where it comes from. Leave a field empty to use the default.</p>
      </div>
      {err ? <p role="alert" className="text-sm text-destructive">{err}</p> : null}
      {GROUPS.map((g) => {
        const rows = limits.filter((l) => l.group === g.id);
        if (!rows.length) return null;
        return (
          <div key={g.id} className="space-y-2" role="group" aria-label={g.title}>
            <h4 className="text-sm font-semibold text-ink">{g.title}</h4>
            <p className="text-xs text-steel">{g.blurb}</p>
            <ul className="divide-y rounded-md border">
              {rows.map((l) => {
                const b = BADGE[l.kind] ?? BADGE.internal;
                const editable = l.editable && l.kind !== 'meta' && l.kind !== 'internal';
                const changed = l.key in draft;
                return (
                  <li key={l.key} data-testid={`limit-${l.key}`} className="grid gap-2 p-3 md:grid-cols-[1.2fr_1fr_1fr]">
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-ink">{l.label}</span>
                        <Badge variant={b.variant}>{b.text}</Badge>
                      </div>
                      {l.note ? <p className="text-xs text-steel">{l.note}</p> : null}
                    </div>
                    <div className="text-sm">
                      <p>Now: <strong>{show(l.effective, l.unit)}</strong></p>
                      <p className="text-xs text-steel">Default: {show(l.default, l.unit)}</p>
                    </div>
                    <div className="flex items-end gap-2">
                      {editable ? (
                        <>
                          <div className="flex-1">{control(l)}</div>
                          <Button
                            variant="ghost" size="sm" aria-label={`Reset ${l.label}`}
                            disabled={!changed && l.source !== 'settings'}
                            onClick={() => setVal(l, null)}
                          >
                            Reset
                          </Button>
                        </>
                      ) : <span className="text-xs text-steel">Read only</span>}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
      <div className="flex gap-2">
        <Button disabled={busy || dirty.length === 0 || invalid} onClick={() => void save()}>{busy ? 'Saving...' : 'Save limits'}</Button>
        <Button variant="outline" disabled={busy || dirty.length === 0} onClick={() => setDraft({})}>Discard changes</Button>
      </div>
    </section>
  );
}
