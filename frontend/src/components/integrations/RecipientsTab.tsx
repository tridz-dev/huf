import { useState } from 'react';
import { Copy, Lock, Plus, Trash2 } from 'lucide-react';
import { toast } from '@/lib/toast';
import { copyText } from '@/lib/clipboard';
import { listSlackChannels, type SlackChannel } from '@/services/integrationApi';
import type { UseFormReturn } from 'react-hook-form';
import { useFieldArray } from 'react-hook-form';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FormField } from '@/components/ui/form';
import { Field, FieldAction, FieldRow } from '@/components/ui/field';
import type { IntegrationFormValues } from './types';

interface RecipientsTabProps {
  form: UseFormReturn<IntegrationFormValues>;
  /** Service key and saved integration name; enables "Load channels" for a saved Slack integration. */
  service?: string;
  settingId?: string;
}

function SlackChannelLoader({ settingId }: { settingId: string }) {
  const [loading, setLoading] = useState(false);
  const [channels, setChannels] = useState<SlackChannel[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setProblem(null);
    try {
      const result = await listSlackChannels(settingId);
      setChannels(result.status === 'Connected' ? result.channels : null);
      if (result.status !== 'Connected') setProblem(result.message || 'Could not load channels.');
    } catch {
      setChannels(null);
      setProblem('Could not load channels. Try again.');
    } finally {
      setLoading(false);
    }
  };

  const copy = async (c: SlackChannel) => {
    if (await copyText(c.id)) toast.success(`Copied the ID of #${c.name}`);
    else toast.error('Could not copy. Select the ID and copy it by hand.');
  };

  return (
    <div className="space-y-3 rounded-lg border p-4" data-testid="slack-channels">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-medium">Slack channels</h4>
          <p className="mt-1 text-sm text-muted-foreground">
            Shows the channels this bot can see, so you can copy a channel ID. Nothing is posted. Needs the channels:read and groups:read permissions; private channels appear once the bot is invited.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={load} disabled={loading} data-testid="slack-load-channels">
          {loading ? 'Loading...' : channels ? 'Reload channels' : 'Load channels'}
        </Button>
      </div>
      {problem && (
        <p className="text-sm text-destructive" role="alert" data-testid="slack-channels-error">{problem}</p>
      )}
      {channels && channels.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="slack-channels-empty">No channels found. Invite the bot to a channel, then reload.</p>
      )}
      {channels && channels.length > 0 && (
        <ul className="max-h-64 divide-y overflow-y-auto rounded-md border" data-testid="slack-channel-list">
          {channels.map((c) => (
            <li key={c.id} className="flex items-center gap-3 px-3 py-2 text-sm" data-testid={`slack-channel-${c.name}`}>
              <span className="min-w-0 flex-1 truncate font-medium">
                #{c.name}
                {c.is_private && <Lock className="ml-1.5 inline h-3 w-3 text-muted-foreground" aria-label="Private channel" />}
              </span>
              <code className="shrink-0 text-xs text-muted-foreground">{c.id}</code>
              <Button type="button" variant="ghost" size="icon" aria-label={`Copy ID of #${c.name}`} data-testid={`slack-copy-id-${c.name}`} onClick={() => copy(c)}>
                <Copy className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function RecipientsTab({ form, service, settingId }: RecipientsTabProps) {
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'recipients',
  });

  return (
    <div className="space-y-4 rounded-lg border p-6">
      {service === 'slack' && settingId && <SlackChannelLoader settingId={settingId} />}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium">Named Recipients</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Define named recipients for this service. The agent can look up a recipient by name and get their service-specific ID (e.g. Telegram Chat ID, Slack User ID, Discord Channel ID).
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            append({ recipient_name: '', recipient_id: '', user: '' })
          }
        >
          <Plus className="w-4 h-4 mr-2" />
          Add recipient
        </Button>
      </div>

      {fields.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-8">
          No recipients configured. Add one so agents can look up IDs by name.
        </p>
      ) : (
        <div className="space-y-4">
          {fields.map((field, index) => (
            <FieldRow
              key={field.id}
              cols={1}
              className="items-start rounded-lg border p-4 md:grid-cols-[1fr_1fr_1fr_auto]"
            >
              <FormField
                control={form.control}
                name={`recipients.${index}.recipient_name`}
                render={({ field: f, fieldState }) => (
                  <Field
                    label="Name"
                    hint="A human-friendly label for this recipient (e.g. John Doe, Sales Alerts, Engineering Team)"
                    error={fieldState.error?.message}
                    reserveNote
                  >
                    <Input {...f} placeholder="e.g. Sales Alerts" />
                  </Field>
                )}
              />
              <FormField
                control={form.control}
                name={`recipients.${index}.recipient_id`}
                render={({ field: f, fieldState }) => (
                  <Field
                    label="Recipient ID"
                    hint="Service-specific ID: Telegram Chat ID, Slack User/Channel ID, Discord Channel ID, email address, etc."
                    error={fieldState.error?.message}
                    reserveNote
                  >
                    <Input {...f} placeholder="Service-specific ID" />
                  </Field>
                )}
              />
              <FormField
                control={form.control}
                name={`recipients.${index}.user`}
                render={({ field: f, fieldState }) => (
                  <Field
                    label="User (optional)"
                    hint="Optionally link to a Frappe User account"
                    error={fieldState.error?.message}
                    reserveNote
                  >
                    <Input {...f} placeholder="Frappe user email" />
                  </Field>
                )}
              />
              <FieldAction reserveNote>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label="Remove recipient"
                  onClick={() => remove(index)}
                  className="text-destructive hover:text-destructive"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </FieldAction>
            </FieldRow>
          ))}
        </div>
      )}
    </div>
  );
}
