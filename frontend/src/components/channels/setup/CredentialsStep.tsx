import { useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { generateVerifyToken, saveWhatsAppCredentials, type WhatsAppCredentials } from './setupApi';

interface FieldDef {
  key: keyof WhatsAppCredentials;
  label: string;
  help: string;
  secret?: boolean;
}

const FIELDS: FieldDef[] = [
  { key: 'phone_number_id', label: 'Phone number ID', help: 'Meta app > WhatsApp > API setup, under the phone number.' },
  { key: 'business_account_id', label: 'WhatsApp Business Account ID (WABA)', help: 'Same page, next to the phone number ID.' },
  { key: 'app_id', label: 'App ID', help: 'Meta app dashboard > App settings > Basic.' },
  { key: 'access_token', label: 'Access token', secret: true, help: 'A permanent system user token from Meta Business settings, with WhatsApp messaging and management access.' },
  { key: 'app_secret', label: 'App secret', secret: true, help: 'Meta app dashboard > App settings > Basic. Lets Huf confirm messages really come from Meta.' },
];

export interface CredentialsStepProps {
  gateway?: string;
  /** Called with the saved gateway name and the verify token to show in the webhook step. */
  onSaved: (gateway: string, verifyToken: string) => void;
  executionUser?: string;
}

export function CredentialsStep({ gateway, onSaved, executionUser }: CredentialsStepProps) {
  const [name, setName] = useState('');
  const [values, setValues] = useState<Record<string, string>>({});
  const [verifyToken] = useState(generateVerifyToken);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const complete = FIELDS.every((f) => (values[f.key] ?? '').trim()) && (gateway || name.trim());

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!complete) return;
    setSaving(true);
    setError(null);
    const res = await saveWhatsAppCredentials({
      gateway,
      name,
      executionUser,
      credentials: { ...(values as unknown as WhatsAppCredentials), webhook_verify_token: verifyToken },
    });
    setSaving(false);
    if (res.ok) onSaved(res.gateway, verifyToken);
    else setError(res.error);
  };

  return (
    <form onSubmit={submit} className="space-y-4" aria-label="WhatsApp credentials">
      {!gateway && (
        <div className="space-y-1.5">
          <Label htmlFor="wa-gw-name">Name for this number</Label>
          <Input id="wa-gw-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Support line" />
          <p className="text-xs text-steel">Only you see this. It labels the number inside Huf.</p>
        </div>
      )}
      {FIELDS.map((f) => (
        <div key={f.key} className="space-y-1.5">
          <Label htmlFor={`wa-${f.key}`}>{f.label}</Label>
          <Input
            id={`wa-${f.key}`}
            type={f.secret ? 'password' : 'text'}
            autoComplete="off"
            value={values[f.key] ?? ''}
            onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
          />
          <p className="text-xs text-steel">{f.help}</p>
        </div>
      ))}
      <p className="text-xs text-steel">
        Huf also generates a webhook verify token for you. You will paste it into Meta in the next step.
      </p>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" disabled={!complete || saving}>
        {saving ? 'Checking with Meta...' : 'Save and check'}
      </Button>
    </form>
  );
}
