import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { CopyField } from '@/components/ui/copy-field';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { updateGateway, type GatewayDoc } from '@/services/gatewayApi';
import type { TabProps } from './CatalogTab';

const PROVIDERS = [
  { value: 'none', label: 'None' },
  { value: 'erpnext', label: 'ERPNext' },
  { value: 'razorpay', label: 'Razorpay' },
  { value: 'stripe', label: 'Stripe' },
];

export const webhookUrl = (origin: string, provider: 'razorpay' | 'stripe', gw: string) =>
  `${origin}/api/method/huf.ai.channels.commerce.payments.${provider}_webhook?gateway=${encodeURIComponent(gw)}`;

export function PaymentsTab({ gw, gateway, onSaved }: TabProps) {
  const [provider, setProvider] = useState(String(gateway?.payment_provider || 'none'));
  const [tpl, setTpl] = useState(String(gateway?.order_confirmed_template ?? ''));
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const origin = typeof window === 'undefined' ? '' : window.location.origin;

  const save = async () => {
    setBusy(true);
    setError('');
    try {
      await updateGateway(gw, { payment_provider: provider, order_confirmed_template: tpl.trim() } as unknown as Partial<GatewayDoc>);
      toast.success('Payments saved');
      onSaved();
    } catch (e) {
      setError(getFrappeErrorMessage(e));
    }
    setBusy(false);
  };

  return (
    <div className="flex max-w-xl flex-col gap-4">
      <Field label="Payment provider" hint="Keys live in the connected integration, never here.">
        {() => (
          <Select value={provider} onValueChange={setProvider}>
            <SelectTrigger aria-label="Payment provider"><SelectValue /></SelectTrigger>
            <SelectContent>{PROVIDERS.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}</SelectContent>
          </Select>
        )}
      </Field>
      <Field label="Order confirmed template" hint="Utility template sent when an order is paid. Empty: free text inside the 24h window.">
        <Input value={tpl} onChange={(e) => setTpl(e.target.value)} />
      </Field>
      <div><Button size="sm" disabled={busy} onClick={() => void save()}>Save</Button></div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <section aria-label="Webhook URLs" className="space-y-3 rounded-sm border border-line p-3">
        <p className="text-xs text-steel">Add these as webhook endpoints in your provider dashboard. The signing secret goes in the integration credentials.</p>
        <CopyField label="Razorpay webhook URL" value={webhookUrl(origin, 'razorpay', gw)} />
        <CopyField label="Stripe webhook URL" value={webhookUrl(origin, 'stripe', gw)} />
      </section>
    </div>
  );
}
