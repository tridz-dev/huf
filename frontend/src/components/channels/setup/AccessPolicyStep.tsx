import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import type { GatewayPolicy } from '@/services/gatewayApi';
import { savePolicy } from './setupApi';

const OPTIONS: { value: GatewayPolicy; title: string; text: string }[] = [
  { value: 'Pairing', title: 'Pairing', text: 'New people get a short code. Nobody is answered until you approve them. Safest start.' },
  { value: 'Allow list', title: 'Allow list', text: 'Only people you approved in advance are answered. Everyone else is silently ignored.' },
  { value: 'Open', title: 'Open', text: 'Anyone who messages this number gets an answer, and every reply can cost you money.' },
];

export function AccessPolicyStep({ gateway, current, onDone }: { gateway: string; current?: string | null; onDone: () => void }) {
  const [policy, setPolicy] = useState<GatewayPolicy>((OPTIONS.find((o) => o.value === current)?.value ?? 'Pairing') as GatewayPolicy);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const finish = async () => {
    setSaving(true);
    setError(null);
    const res = await savePolicy(gateway, policy);
    setSaving(false);
    if (res.ok) onDone();
    else setError(res.error);
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-steel">Choose who can talk to your agent in direct messages.</p>
      <RadioGroup value={policy} onValueChange={(v) => setPolicy(v as GatewayPolicy)} aria-label="Who can message this number">
        {OPTIONS.map((o) => (
          <div key={o.value} className="flex items-start gap-3 rounded-md border border-line p-3">
            <RadioGroupItem id={`pol-${o.value}`} value={o.value} className="mt-0.5" />
            <Label htmlFor={`pol-${o.value}`} className="space-y-0.5">
              <span className="block text-sm font-medium text-ink">{o.title}</span>
              <span className="block text-sm font-normal text-steel">{o.text}</span>
            </Label>
          </div>
        ))}
      </RadioGroup>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button onClick={finish} disabled={saving}>
        {saving ? 'Saving...' : 'Finish setup'}
      </Button>
    </div>
  );
}
