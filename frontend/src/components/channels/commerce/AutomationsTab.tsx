import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { updateGateway, type GatewayDoc } from '@/services/gatewayApi';
import { submitTemplatesPack, type PackResult } from '@/services/commerceApi';
import type { TabProps } from './CatalogTab';

export function CommerceAutomationsTab({ gw, gateway, onSaved }: TabProps) {
  const [hours, setHours] = useState(String(gateway?.cart_recovery_hours ?? 0));
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [pack, setPack] = useState<PackResult | null>(null);

  const save = async () => {
    setBusy(true);
    setError('');
    try {
      await updateGateway(gw, { cart_recovery_hours: Math.max(0, Math.floor(Number(hours) || 0)) } as unknown as Partial<GatewayDoc>);
      toast.success('Cart recovery saved');
      onSaved();
    } catch (e) {
      setError(getFrappeErrorMessage(e));
    }
    setBusy(false);
  };

  const submit = async () => {
    setSubmitting(true);
    setError('');
    const res = await submitTemplatesPack(gw);
    setSubmitting(false);
    if (!res.ok) return setError(res.error);
    setPack(res.data);
  };

  return (
    <div className="flex max-w-xl flex-col gap-4">
      <Field label="Cart recovery after (hours)" hint="One cart_reminder template for Draft orders still unpaid after this long. 0 = off.">
        <Input type="number" min={0} value={hours} onChange={(e) => setHours(e.target.value)} />
      </Field>
      <div><Button size="sm" disabled={busy} onClick={() => void save()}>Save</Button></div>
      <section aria-label="Utility templates pack" className="space-y-2 rounded-sm border border-line p-3">
        <p className="text-sm text-ink">COD confirmation, order, payment and cart reminders as utility templates.</p>
        <Button size="sm" variant="outline" disabled={submitting} onClick={() => void submit()}>
          {submitting && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}Submit utility templates pack
        </Button>
        {pack && (
          <ul aria-label="Pack results" className="space-y-1 text-xs">
            {pack.success === false && <li className="text-destructive">{pack.error}</li>}
            {Object.entries(pack.results ?? {}).map(([name, r]) => (
              <li key={name} className="flex justify-between">
                <span className="font-mono text-ink">{name}</span>
                <span className={r?.success === false ? 'text-destructive' : 'text-steel'}>{r?.success === false ? r.error || r.message || 'failed' : 'submitted'}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
