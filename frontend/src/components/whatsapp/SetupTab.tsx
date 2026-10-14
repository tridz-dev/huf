import { toast } from 'sonner';
import { AlertTriangle, Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { StatusDot } from '@/components/ui/status-dot';
import type { SetupStatus } from '@/services/whatsappApi';

function Check({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs ${ok ? 'text-steel' : 'text-destructive'}`}>
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${ok ? 'bg-good' : 'bg-destructive'}`} />
      {label}: {ok ? 'OK' : 'failing'}
    </span>
  );
}

const CHECK_LABELS: Record<string, string> = {
  app_secret_missing: 'The app secret is not set, so incoming messages cannot be verified until you add it.',
  webhook_verify_token_missing: 'The verification token is not set, so Meta cannot confirm this webhook until you add it.',
  account_phone_mismatch:
    'The linked WhatsApp Account uses a different phone number than this gateway. Messages for it would be ignored. Link the matching account or fix the phone number ID.',
};

function checkLabel(code: string): string {
  return CHECK_LABELS[code] ?? 'A setup check is failing for this gateway.';
}

export function SetupTab({ status }: { status: SetupStatus }) {
  const copy = (url: string) => {
    navigator.clipboard
      .writeText(url)
      .then(() => toast.success('Webhook URL copied'))
      .catch(() => toast.error('Could not copy. Select the URL and copy it manually.'));
  };

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-ink">Bridge</h3>
        <StatusDot status={status.bridge_available ? 'healthy' : 'held'} />
        <p className="text-xs text-steel">
          {status.bridge_available
            ? 'The optional WhatsApp Business app connector is installed, so template management and message history are available.'
            : 'Template management and message history need the optional WhatsApp Business app connector ("bridge mode"). It is not installed, so those features are unavailable. Replies still work without it.'}
        </p>
        <p className="text-xs text-steel">
          Use one gateway per Meta app and phone number. The connector's own webhook stays live and is not signature-checked, so restrict it at your reverse proxy (see the setup guide).
        </p>
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-ink">Accounts</h3>
        {status.accounts.length === 0 ? (
          <p className="text-xs text-steel">No WhatsApp Accounts found.</p>
        ) : (
          <ul className="divide-y divide-line rounded-sm border border-line">
            {status.accounts.map((a) => (
              <li key={a.name} className="flex items-center justify-between px-3 py-2 text-xs">
                <span className="text-ink">{a.name}</span>
                <span className="font-mono text-steel">
                  {a.phone_id || 'no phone id'} {a.status ? `· ${a.status}` : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-ink">Gateways</h3>
        {status.gateways.length === 0 && <p className="text-xs text-steel">No WhatsApp gateways configured.</p>}
        {status.gateways.map((g) => (
          <div key={g.name} className="space-y-2 rounded-sm border border-line p-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-ink">{g.name}</span>
              <span className="text-xs text-steel">{g.enabled ? 'Enabled' : 'Disabled'}</span>
            </div>
            <div className="flex flex-wrap gap-4">
              <Check ok={!g.app_secret_missing} label="App secret" />
              <Check ok={g.verify_token_present} label="Verification token" />
              <span className="text-xs text-steel">Account: {g.whatsapp_account || 'none'}</span>
            </div>
            {(g.failing_checks ?? []).map((code) => (
              <p key={code} className="text-xs text-destructive">
                {checkLabel(code)}
              </p>
            ))}
            <div className="flex gap-2">
              <Input readOnly value={g.webhook_url} className="font-mono text-xs" aria-label={`Webhook URL for ${g.name}`} />
              <Button type="button" variant="outline" size="icon" onClick={() => copy(g.webhook_url)} aria-label="Copy webhook URL">
                <Copy className="h-4 w-4" />
              </Button>
            </div>
            <p className="flex items-start gap-1.5 text-xs text-steel">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-signal-ink" />
              {g.callback_warning}
            </p>
          </div>
        ))}
      </section>
    </div>
  );
}
