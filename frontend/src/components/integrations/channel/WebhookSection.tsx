import { RefreshCw } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CopyField } from '@/components/ui/copy-field';
import { cn } from '@/lib/utils';
import { getGatewayWebhookUrl } from '@/utils/gatewayWebhook';
import type { GatewayDoc } from '@/services/gatewayApi';

export interface TelegramWebhookState {
  url?: string;
  status?: string;
  lastSetup?: string;
}

interface WebhookSectionProps {
  gateway: GatewayDoc;
  telegramWebhook: TelegramWebhookState;
  settingUpWebhook: boolean;
  onSetupTelegramWebhook: () => void;
}

export function WebhookSection({
  gateway,
  telegramWebhook,
  settingUpWebhook,
  onSetupTelegramWebhook,
}: WebhookSectionProps) {
  return (
    <div className="space-y-2 rounded-lg border p-4">
      <p className="text-sm font-medium">Inbound webhook URL</p>
      <p className="text-xs text-muted-foreground">
        {gateway.provider === 'WhatsApp'
          ? 'In your Meta app, open WhatsApp > Configuration, paste this as the callback URL with your verify token, then subscribe to the messages field.'
          : "Paste this URL into the channel provider's webhook settings."}
      </p>
      <CopyField label="Webhook URL" value={getGatewayWebhookUrl(gateway.name, gateway.provider)} />
      {gateway.provider === 'WhatsApp' && (
        <p className="text-xs text-muted-foreground">
          Use this URL, not the one from the WhatsApp connector app. Meta sends each app&apos;s messages to one
          URL, and only this one reaches your agent. Message history and templates still fill in.
        </p>
      )}

      {gateway.provider === 'Telegram' && (
        <div className="mt-3 space-y-2 border-t pt-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="text-xs text-muted-foreground">
              Telegram also needs its webhook registered with the Bot API before it starts
              delivering messages.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onSetupTelegramWebhook}
              disabled={settingUpWebhook}
            >
              <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', settingUpWebhook && 'animate-spin')} />
              {settingUpWebhook ? 'Setting up...' : 'Setup Webhook'}
            </Button>
          </div>
          {telegramWebhook.status && (
            <Badge
              variant={
                telegramWebhook.status.toLowerCase().includes('fail') ||
                telegramWebhook.status.toLowerCase().includes('error')
                  ? 'destructive'
                  : telegramWebhook.status.toLowerCase().includes('configured') ||
                    telegramWebhook.status.toLowerCase().includes('already')
                  ? 'success'
                  : 'secondary'
              }
            >
              {telegramWebhook.status}
            </Badge>
          )}
          {telegramWebhook.lastSetup && (
            <p className="text-xs text-muted-foreground">
              Last setup attempt: {new Date(telegramWebhook.lastSetup).toLocaleString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
