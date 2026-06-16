import { RefreshCw } from 'lucide-react';
import type { UseFormReturn } from 'react-hook-form';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import { LinkFieldControl } from '@/components/ui/link-field-control';
import { linkRoutes } from '@/lib/link-routes';
import type { IntegrationFormValues } from './types';

interface TelegramTabProps {
  form: UseFormReturn<IntegrationFormValues>;
  agents: Array<{ name: string; agent_name: string }>;
  webhookUrl?: string;
  webhookStatus?: string;
  lastWebhookSetup?: string;
  settingUpWebhook: boolean;
  onSetupWebhook: () => void;
}

function getWebhookStatusVariant(status?: string): 'default' | 'secondary' | 'destructive' {
  if (!status) return 'secondary';
  const lower = status.toLowerCase();
  if (lower.includes('fail') || lower.includes('error')) return 'destructive';
  if (lower.includes('configured') || lower.includes('already')) return 'default';
  return 'secondary';
}

export function TelegramTab({
  form,
  agents,
  webhookUrl,
  webhookStatus,
  lastWebhookSetup,
  settingUpWebhook,
  onSetupWebhook,
}: TelegramTabProps) {
  const isHttps = webhookUrl?.startsWith('https://');

  return (
    <div className="space-y-6 rounded-lg border p-6">
      <FormField
        control={form.control}
        name="telegram_agent"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Responding Agent</FormLabel>
            <FormControl>
              <LinkFieldControl value={field.value} linkTo={linkRoutes.agent}>
                <Select onValueChange={field.onChange} value={field.value || ''}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select an agent for incoming messages" />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map((agent) => (
                      <SelectItem key={agent.name} value={agent.name}>
                        {agent.agent_name || agent.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </LinkFieldControl>
            </FormControl>
            <FormDescription>
              The HUF agent that responds to messages received by this Telegram bot.
            </FormDescription>
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="telegram_auto_setup_webhook"
        render={({ field }) => (
          <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
            <div className="space-y-0.5">
              <FormLabel>Auto setup webhook on save</FormLabel>
              <FormDescription>
                Automatically register the webhook with Telegram when this integration is saved.
              </FormDescription>
            </div>
            <FormControl>
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            </FormControl>
          </FormItem>
        )}
      />

      <div className="space-y-4 rounded-lg border p-4 bg-muted/30">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <h3 className="text-sm font-medium">Webhook Configuration</h3>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onSetupWebhook}
            disabled={settingUpWebhook}
          >
            <RefreshCw className={cn('w-4 h-4 mr-2', settingUpWebhook && 'animate-spin')} />
            {settingUpWebhook ? 'Setting up...' : 'Setup Webhook'}
          </Button>
        </div>

        {webhookStatus && (
          <Badge variant={getWebhookStatusVariant(webhookStatus)}>{webhookStatus}</Badge>
        )}

        {!isHttps && webhookUrl && (
          <p className="text-sm text-destructive">
            Telegram requires a public HTTPS URL. The current webhook URL may not work on localhost.
          </p>
        )}

        <div className="space-y-2">
          <FormLabel>Webhook URL</FormLabel>
          <Input readOnly value={webhookUrl || ''} className="bg-muted font-mono text-xs" />
        </div>

        {lastWebhookSetup && (
          <p className="text-xs text-muted-foreground">
            Last setup attempt: {new Date(lastWebhookSetup).toLocaleString()}
          </p>
        )}
      </div>
    </div>
  );
}
