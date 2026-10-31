import { useCallback, useEffect, useMemo, useState } from 'react';
import { Combobox, type ComboboxOption } from '../ui/combobox';
import { Label } from '../ui/label';
import { listSlackChannels } from '@/services/integrationApi';
import { useIntegrationStatus } from '@/lib/flow/flowIntegrations';

/** The channels of the connected Slack workspace, read once a minute at most (reading never posts anything). */
let cache: { at: number; options: ComboboxOption[] } | null = null;
const FRESH_MS = 60_000;

/** Which listed channel a stored value means: its id (`C0123`) or its name with or without `#`. */
export function channelFor(options: ComboboxOption[] | null, value: string): ComboboxOption | undefined {
  const bare = value.trim().replace(/^#/, '').toLowerCase();
  if (!bare) return undefined;
  return (options ?? []).find((o) => o.value.toLowerCase() === bare || o.label.replace(/^#/, '').toLowerCase() === bare);
}

/** Reads the channel list when `enabled` (or when `load()` is called). `failed` means typing the name is the only way. */
export function useSlackChannels(enabled: boolean) {
  const [options, setOptions] = useState<ComboboxOption[] | null>(cache && Date.now() - cache.at < FRESH_MS ? cache.options : null);
  const [loading, setLoading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    setProblem(null);
    try {
      const result = await listSlackChannels();
      if (result.status === 'Connected') {
        const list = result.channels.map((c) => ({ value: c.id, label: `#${c.name}`, subtitle: c.is_private ? 'Private channel' : undefined }));
        cache = { at: Date.now(), options: list };
        setOptions(list);
      } else setProblem(result.message || 'Could not load channels.');
    } catch {
      setProblem('Could not load channels. Type the channel name instead.');
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    if (enabled && !options) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);
  return { options, loading, problem, failed: problem !== null, load };
}

/**
 * The channel list for a Slack step, shown only when Slack is connected. Channels are read the first time the list is
 * opened (or, with `eager`, as soon as the step opens so the chosen channel shows its name).
 */
export function SlackChannelPicker({
  value, onPick, label = 'Or pick a channel', testId = 'flow-field-slack-channel-pick', eager, channels,
}: {
  value: string;
  onPick: (channelId: string) => void;
  label?: string;
  testId?: string;
  eager?: boolean;
  /** The list, when the form already reads it (so it is read once). */
  channels?: ReturnType<typeof useSlackChannels>;
}) {
  const status = useIntegrationStatus();
  const connected = !!status.slack?.connected;
  const own = useSlackChannels(connected && !!eager && !channels);
  const { options, loading, problem, load } = channels ?? own;
  const [search, setSearch] = useState('');
  const shown = useMemo(() => {
    const q = search.trim().toLowerCase().replace(/^#/, '');
    return (options ?? []).filter((o) => !q || o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q));
  }, [options, search]);

  if (!connected) return null;

  const chosen = channelFor(options, value);
  return (
    <div data-testid="flow-slack-channel-picker">
      <Label htmlFor="slack-channel-pick" size="sm">{label}</Label>
      <Combobox
        id="slack-channel-pick"
        testId={testId}
        options={shown}
        shouldFilter={false}
        onSearchChange={setSearch}
        value={chosen?.value ?? ''}
        onValueChange={(v) => v && onPick(v)}
        onOpenChange={(open) => { if (open && !options && !loading) void load(); }}
        placeholder={loading ? 'Loading channels...' : chosen ? chosen.label : value ? value : 'Choose a channel'}
        searchPlaceholder="Search channels..."
        emptyText={loading ? 'Loading channels...' : problem ?? 'No matching channel. Type its name instead.'}
      />
      {problem && <p className="mt-1 text-xs text-destructive" role="alert" data-testid="flow-slack-channel-picker-error">{problem}</p>}
    </div>
  );
}
