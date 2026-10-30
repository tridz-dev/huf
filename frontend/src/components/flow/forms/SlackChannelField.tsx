import { type ReactNode, useState } from 'react';
import { Button } from '../../ui/button';
import { DataInput } from '../data/DataInput';
import { FieldHint } from '../FieldHint';
import { SlackChannelPicker, channelFor, useSlackChannels } from '../SlackChannelPicker';
import { useIntegrationStatus } from '@/lib/flow/flowIntegrations';

/**
 * One control for the Slack channel: pick it from the connected workspace, or (when Slack is not connected, the list
 * cannot be read, or the channel comes from earlier data) type it. The person can always switch between the two.
 */
export function SlackChannelField({
  value, onChange, nodeId, testId, Err, hint,
}: {
  value: unknown;
  onChange: (v: unknown) => void;
  nodeId: string;
  testId: string;
  Err: ReactNode;
  hint: string;
}) {
  const status = useIntegrationStatus();
  const connected = !!status.slack?.connected;
  const channels = useSlackChannels(connected);
  const [choice, setChoice] = useState<'pick' | 'type' | null>(null);
  const text = typeof value === 'string' ? value : '';
  const isData = value !== undefined && value !== null && typeof value !== 'string';
  const listed = channelFor(channels.options, text);
  // Typing is the way when there is no list to pick from, or the value is not one of its channels (a name nobody listed, data).
  const mustType = !connected || channels.failed || isData || (text !== '' && channels.options !== null && !listed);
  const mode = choice ?? (mustType ? 'type' : 'pick');

  if (mode === 'type') {
    return (
      <div data-testid="flow-slack-channel-field" data-mode="type">
        <DataInput id="tool-in-channel" nodeId={nodeId} testId={testId} label="Channel" placeholder="#general" hint={hint} value={value} onChange={(v) => { setChoice('type'); onChange(v); }} />
        {Err}
        {connected && !channels.failed && !isData && (
          <Button type="button" variant="link" size="sm" className="h-auto px-0 text-xs" data-testid="flow-slack-channel-use-list" onClick={() => setChoice('pick')}>
            Pick from your channels
          </Button>
        )}
      </div>
    );
  }
  return (
    <div data-testid="flow-slack-channel-field" data-mode="pick">
      <SlackChannelPicker label="Channel" testId={testId} channels={channels} value={text} onPick={onChange} />
      <FieldHint testId="flow-hint-slack-channel">{hint}</FieldHint>
      {Err}
      <Button type="button" variant="link" size="sm" className="h-auto px-0 text-xs" data-testid="flow-slack-channel-type-it" onClick={() => setChoice('type')}>
        Type the channel name instead
      </Button>
    </div>
  );
}
