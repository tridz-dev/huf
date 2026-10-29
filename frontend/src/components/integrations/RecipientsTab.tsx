import { useCallback, useEffect, useRef, useState } from 'react';
import { Copy, Loader2, Lock, Plus, Trash2 } from 'lucide-react';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
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

type ChannelsState =
  | { kind: 'loading' }
  | { kind: 'ready'; channels: SlackChannel[] }
  | { kind: 'error'; message: string; needsCredentials?: boolean };

/** Read-only list of the channels the bot can see. Loads when the tab opens; always ends in a list, an empty note or an error with Try again. */
function SlackChannelLoader({ settingId, onUse }: { settingId: string; onUse: (channel: SlackChannel) => void }) {
  const [state, setState] = useState<ChannelsState>({ kind: 'loading' });
  const [search, setSearch] = useState('');
  const run = useRef(0);

  const load = useCallback(async () => {
    const mine = ++run.current;
    setState({ kind: 'loading' });
    try {
      const result = await listSlackChannels(settingId);
      if (mine !== run.current) return;
      if (result.status === 'Connected') setState({ kind: 'ready', channels: result.channels });
      else
        setState({
          kind: 'error',
          message: result.message || 'Could not load channels.',
          needsCredentials: result.status === 'Not connected',
        });
    } catch (error) {
      if (mine !== run.current) return;
      setState({ kind: 'error', message: getFrappeErrorMessage(error) || 'Could not load channels. Try again.' });
    }
  }, [settingId]);

  useEffect(() => {
    void load();
    return () => {
      run.current += 1;
    };
  }, [load]);

  const copy = async (c: SlackChannel) => {
    if (await copyText(c.id)) toast.success(`Copied the ID of #${c.name}`);
    else toast.error('Could not copy. Select the ID and copy it by hand.');
  };

  const channels = state.kind === 'ready' ? state.channels : [];
  const shown = channels.filter((c) => !search.trim() || c.name.toLowerCase().includes(search.trim().toLowerCase().replace(/^#/, '')));

  return (
    <div className="space-y-3 rounded-lg border p-4" data-testid="slack-channels">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="text-sm font-medium">Channels in your Slack workspace</h4>
          <p className="mt-1 text-sm text-muted-foreground">
            The channels this bot can see. Nothing is posted. Private channels appear once the bot is invited to them.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={load} disabled={state.kind === 'loading'} data-testid="slack-load-channels">
          {state.kind === 'loading' ? 'Loading...' : 'Reload'}
        </Button>
      </div>

      {state.kind === 'loading' && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status" data-testid="slack-channels-loading">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading channels from Slack...
        </p>
      )}

      {state.kind === 'error' && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-destructive/30 bg-destructive-tint px-3 py-2" role="alert" data-testid="slack-channels-error">
          <p className="min-w-0 flex-1 break-words text-sm text-destructive">{state.message}</p>
          {!state.needsCredentials && (
            <Button type="button" size="sm" variant="outline" onClick={load} data-testid="slack-channels-retry">
              Try again
            </Button>
          )}
        </div>
      )}

      {state.kind === 'ready' && channels.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="slack-channels-empty">
          The bot cannot see any channel yet. Invite it to a channel in Slack (type /invite @your-bot there), then press Reload.
        </p>
      )}

      {state.kind === 'ready' && channels.length > 0 && (
        <>
          {channels.length > 6 && (
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search channels..." aria-label="Search channels" />
          )}
          <ul className="max-h-64 divide-y overflow-y-auto rounded-md border" data-testid="slack-channel-list">
            {shown.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm" data-testid={`slack-channel-${c.name}`}>
                <span className="min-w-0 flex-1 truncate font-medium">
                  #{c.name}
                  {c.is_private && <Lock className="ml-1.5 inline h-3 w-3 text-muted-foreground" aria-label="Private channel" />}
                </span>
                <Button type="button" variant="ghost" size="sm" onClick={() => onUse(c)} data-testid={`slack-use-${c.name}`}>
                  Save as recipient
                </Button>
                <Button type="button" variant="ghost" size="sm" aria-label={`Copy ID of #${c.name}`} data-testid={`slack-copy-id-${c.name}`} onClick={() => copy(c)}>
                  <Copy className="mr-1 h-3.5 w-3.5" /> Copy ID
                </Button>
              </li>
            ))}
            {shown.length === 0 && <li className="px-3 py-2 text-sm text-muted-foreground">No channel matches that search.</li>}
          </ul>
        </>
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
      {service === 'slack' && settingId && (
        <SlackChannelLoader
          settingId={settingId}
          onUse={(c) => {
            const exists = fields.some((f) => f.recipient_id === c.id);
            if (exists) {
              toast.info(`#${c.name} is already saved as a recipient`);
              return;
            }
            append({ recipient_name: `#${c.name}`, recipient_id: c.id, user: '' });
            toast.success(`#${c.name} added. Press Save to keep it.`);
          }}
        />
      )}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium">Saved recipients</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Give a channel or person a friendly name, so steps and agents can pick it by name instead of an ID.
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
          No saved recipients yet. Add one to pick it by name later.
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
