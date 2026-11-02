import { Check, Loader2 } from 'lucide-react';
import { CopyField } from '@/components/ui/copy-field';
import { getGatewayWebhookUrl } from '@/utils/gatewayWebhook';

const FIELDS = ['messages', 'message_template_status_update', 'account_update', 'phone_number_quality_update'];

export interface WebhookStepProps {
  gateway: string;
  webhookUrl?: string;
  verifyToken?: string | null;
  verified: boolean;
}

export function WebhookStep({ gateway, webhookUrl, verifyToken, verified }: WebhookStepProps) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-steel">
        In your Meta app, open WhatsApp &gt; Configuration, edit the webhook, and paste these two values.
      </p>
      <CopyField label="Callback URL" value={webhookUrl || getGatewayWebhookUrl(gateway, 'WhatsApp')} />
      {verifyToken ? (
        <CopyField label="Verify token" value={verifyToken} masked />
      ) : (
        <p className="text-sm text-steel">
          Use the verify token you saved with the credentials. Lost it? Set a new one under Settings, Credentials.
        </p>
      )}
      <div>
        <p className="text-sm font-medium text-ink">Then subscribe to these fields</p>
        <ul className="mt-1 list-inside list-disc font-mono text-xs text-ink">
          {FIELDS.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      </div>
      <p role="status" className="flex items-center gap-2 text-sm text-ink">
        {verified ? (
          <>
            <Check className="h-4 w-4 text-good" aria-hidden /> Meta verified the webhook.
          </>
        ) : (
          <>
            <Loader2 className="h-4 w-4 animate-spin text-steel" aria-hidden /> Waiting for Meta to verify...
          </>
        )}
      </p>
    </div>
  );
}
