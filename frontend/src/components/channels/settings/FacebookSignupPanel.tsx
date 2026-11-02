import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { getSignupSettings, saveSignupSettings, type SignupSettings } from '@/services/channels/embeddedSignupApi';

const MODES = [
  { value: 'direct', label: 'Direct (this site owns the Facebook app)' },
  { value: 'broker', label: 'Broker (Huf Cloud issues tokens)' },
  { value: 'broker_server', label: 'Broker server (this site is the broker)' },
] as const;

/** Site-wide Embedded Signup settings. Secrets are write-only: shown as set / not set, never read back. */
export function FacebookSignupPanel() {
  const [s, setS] = useState<SignupSettings | null>(null);
  const [appSecret, setAppSecret] = useState('');
  const [brokerKey, setBrokerKey] = useState('');
  const [verifyToken, setVerifyToken] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let live = true;
    getSignupSettings()
      .then((v) => live && setS(v))
      .catch((e) => live && setError(getFrappeErrorMessage(e) || 'Could not load the settings.'));
    return () => {
      live = false;
    };
  }, []);

  if (!s) {
    return error ? (
      <p role="alert" className="text-sm text-destructive">{error}</p>
    ) : (
      <p className="text-sm text-steel">Loading...</p>
    );
  }
  const set = <K extends keyof SignupSettings>(k: K, v: SignupSettings[K]) => setS({ ...s, [k]: v });

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const next = await saveSignupSettings({
        enabled: s.enabled,
        mode: s.mode,
        facebook_app_id: s.facebook_app_id,
        config_id: s.config_id,
        graph_version: s.graph_version,
        broker_url: s.broker_url,
        tenant_id: s.tenant_id,
        ...(appSecret ? { app_secret: appSecret } : {}),
        ...(brokerKey ? { broker_api_key: brokerKey } : {}),
        ...(verifyToken ? { broker_verify_token: verifyToken } : {}),
      });
      setS(next);
      setAppSecret('');
      setBrokerKey('');
      setVerifyToken('');
      toast.success('Facebook signup settings saved');
    } catch (e) {
      setError(getFrappeErrorMessage(e) || 'Could not save.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader><CardTitle className="text-sm">Facebook signup</CardTitle></CardHeader>
      <CardContent className="grid max-w-xl gap-3">
        <p className="text-xs text-steel">
          Lets people connect a WhatsApp number with "Connect with Facebook" instead of pasting keys. Needs a Meta app approved as a Tech Provider.
        </p>
        <Field label="Enabled" size="sm">
          {(fp) => <div className="flex h-control-md items-center"><Switch {...fp} checked={s.enabled} onCheckedChange={(v) => set('enabled', v)} /></div>}
        </Field>
        <Field label="Mode" size="sm">
          {(fp) => (
            <Select value={s.mode} onValueChange={(v) => set('mode', v as SignupSettings['mode'])}>
              <SelectTrigger {...fp}><SelectValue /></SelectTrigger>
              <SelectContent>
                {MODES.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
              </SelectContent>
            </Select>
          )}
        </Field>
        <Field label="Facebook app ID" size="sm">
          {(fp) => <Input {...fp} value={s.facebook_app_id} onChange={(e) => set('facebook_app_id', e.target.value)} />}
        </Field>
        <Field label="Configuration ID" size="sm">
          {(fp) => <Input {...fp} value={s.config_id} onChange={(e) => set('config_id', e.target.value)} />}
        </Field>
        <Field label="Graph API version" size="sm">
          {(fp) => <Input {...fp} value={s.graph_version} onChange={(e) => set('graph_version', e.target.value)} />}
        </Field>
        {s.mode !== 'broker' && (
          <Field label={`Facebook app secret (${s.app_secret_set ? 'set' : 'not set'})`} size="sm">
            {(fp) => (
              <Input {...fp} type="password" autoComplete="new-password" value={appSecret} onChange={(e) => setAppSecret(e.target.value)}
                placeholder={s.app_secret_set ? 'Leave empty to keep the current secret' : ''} />
            )}
          </Field>
        )}
        {s.mode === 'broker' && (
          <>
            <Field label="Broker URL" size="sm">
              {(fp) => <Input {...fp} value={s.broker_url} onChange={(e) => set('broker_url', e.target.value)} placeholder="https://" />}
            </Field>
            <Field label="Tenant ID" size="sm">
              {(fp) => <Input {...fp} value={s.tenant_id} onChange={(e) => set('tenant_id', e.target.value)} />}
            </Field>
            <Field label={`Broker API key (${s.broker_api_key_set ? 'set' : 'not set'})`} size="sm">
              {(fp) => (
                <Input {...fp} type="password" autoComplete="new-password" value={brokerKey} onChange={(e) => setBrokerKey(e.target.value)}
                  placeholder={s.broker_api_key_set ? 'Leave empty to keep the current key' : ''} />
              )}
            </Field>
          </>
        )}
        {s.mode === 'broker_server' && (
          <>
            <Field label="Broker webhook callback URL" size="sm">
              {(fp) => <Input {...fp} readOnly value={s.broker_callback_url} onFocus={(e) => e.currentTarget.select()} />}
            </Field>
            <Field label={`Webhook verify token (${s.broker_verify_token_set ? 'set' : 'not set'})`} size="sm">
              {(fp) => (
                <Input {...fp} type="password" autoComplete="new-password" value={verifyToken} onChange={(e) => setVerifyToken(e.target.value)}
                  placeholder={s.broker_verify_token_set ? 'Leave empty to keep the current token' : ''} />
              )}
            </Field>
            <p className="text-xs text-steel">Set the callback URL and verify token as the webhook of your Meta app. Events are verified here and forwarded to the tenant that owns each WhatsApp account.</p>
          </>
        )}
        {s.mode === 'broker_server' && (
          <p className="text-xs text-steel">Tenant keys are created with the create_tenant_key API method (see docs/WHATSAPP_EMBEDDED_SIGNUP.md). They are shown once and stored hashed.</p>
        )}
        {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
        <div>
          <Button size="sm" onClick={() => void save()} disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />}
            Save
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
