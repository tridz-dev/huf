import { Link } from 'react-router-dom';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { Label } from '../../ui/label';
import { CHANNELS } from '../../channels/channelsMeta';
import { channelNoun, connectWords, gatewaysForKind, pickPrompt, type GatewayKindId } from '@/lib/flow-gateway/gatewayWords';
import type { GatewayChoice } from '@/lib/flow-gateway/gatewayTrigger.types';

/** "whatsapp" -> "WhatsApp": the channel's own display name, never a raw provider id. */
const providerName = (provider: string): string => CHANNELS.find((c) => c.key === provider.toLowerCase() || c.label.toLowerCase() === provider.toLowerCase())?.label ?? provider;

interface Props {
  kind: GatewayKindId;
  value: string;
  gateways: readonly GatewayChoice[];
  onChange: (name: string) => void;
  disabled?: boolean;
}

/** "Which WhatsApp number?": only the channels of the right kind this person may use, or the way to connect one. */
export function GatewayChooser({ kind, value, gateways, onChange, disabled }: Props) {
  const options = gatewaysForKind(kind, gateways);
  const noun = channelNoun(kind);
  const channel = CHANNELS.find((c) => c.key === kind);

  if (options.length === 0 && !value) {
    return (
      <div className="space-y-2 rounded-md border border-dashed border-border p-3" data-testid="flow-gateway-none">
        <p className="text-sm">No {noun} is connected yet.</p>
        <p className="text-meta text-muted-foreground">Connect one first, then come back and pick it here. You can keep building meanwhile.</p>
        <Link
          to={channel?.setupHref ?? '/gateways'}
          className="inline-block text-sm font-medium text-primary underline underline-offset-2"
          data-testid="flow-gateway-connect"
        >
          {connectWords(kind)}
        </Link>
      </div>
    );
  }
  const staleName = (gateways.find((g) => g.name === value)?.label || 'A channel that is no longer available') + (gateways.some((g) => g.name === value) ? ' (not available)' : '');
  const known = options.some((g) => g.name === value);
  return (
    <div data-testid="flow-gateway-chooser">
      <Label htmlFor="flow-gateway-select" size="sm">{kind === 'gateway' ? 'Which channel?' : `Which ${noun}?`}</Label>
      <div className="mt-1">
        <Select value={value || undefined} onValueChange={onChange} disabled={disabled}>
          <SelectTrigger id="flow-gateway-select" data-testid="flow-gateway-select">
            <SelectValue placeholder={pickPrompt(kind)} />
          </SelectTrigger>
          <SelectContent>
            {options.map((g) => (
              <SelectItem key={g.name} value={g.name} data-testid={`flow-option-gateway-${g.name}`}>
                {g.label}
                {kind === 'gateway' && g.provider ? ` (${providerName(g.provider)})` : ''}
                {g.enabled ? '' : ' (switched off)'}
              </SelectItem>
            ))}
            {value && !known ? (
              <SelectItem value={value} data-testid={`flow-option-gateway-${value}`}>{staleName}</SelectItem>
            ) : null}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
