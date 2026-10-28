import { useState } from 'react';
import { Combobox, type ComboboxOption } from '../ui/combobox';
import { Label } from '../ui/label';
import { listSlackChannels } from '@/services/integrationApi';
import { useIntegrationStatus } from '@/lib/flowIntegrations';

/**
 * "Pick a channel" list for a Slack step, shown only when Slack is connected. Channels are read (never posted to)
 * the first time the list is opened. Typing the channel by hand in the field above keeps working.
 */
export function SlackChannelPicker({ value, onPick }: { value: string; onPick: (channelId: string) => void }) {
  const status = useIntegrationStatus();
  const [options, setOptions] = useState<ComboboxOption[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  if (!status.slack?.connected) return null;

  const load = async () => {
    setLoading(true);
    setProblem(null);
    try {
      const result = await listSlackChannels();
      if (result.status === 'Connected') {
        setOptions(result.channels.map((c) => ({ value: c.id, label: `#${c.name}`, subtitle: c.is_private ? `Private · ${c.id}` : c.id })));
      } else {
        setProblem(result.message || 'Could not load channels.');
      }
    } catch {
      setProblem('Could not load channels. Type the channel name or ID above instead.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="flow-slack-channel-picker">
      <Label htmlFor="slack-channel-pick" size="sm">Or pick a channel</Label>
      <Combobox
        id="slack-channel-pick"
        testId="flow-field-slack-channel-pick"
        options={options ?? []}
        value={options?.some((o) => o.value === value) ? value : ''}
        onValueChange={(v) => v && onPick(v)}
        onOpenChange={(open) => { if (open && !options && !loading) void load(); }}
        placeholder={loading ? 'Loading channels...' : 'Search channels...'}
        searchPlaceholder="Search channels..."
        emptyText={loading ? 'Loading...' : 'No matching channel. Type its name or ID above.'}
        disabled={loading}
      />
      {problem && <p className="mt-1 text-xs text-destructive" role="alert" data-testid="flow-slack-channel-picker-error">{problem}</p>}
    </div>
  );
}
