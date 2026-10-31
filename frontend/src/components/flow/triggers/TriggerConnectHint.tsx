import { Link } from 'react-router-dom';
import { CHANNELS } from '../../channels/channelsMeta';
import { channelNoun, gatewaysForKind, type GatewayKindId } from '@/lib/flow-gateway/gatewayWords';
import type { GatewayChoice } from '@/lib/flow-gateway/gatewayTrigger.types';

/**
 * Under a WhatsApp or Telegram card when nothing of that kind is connected yet: says so and links to the setup.
 * Choosing the card still works (the flow saves as a draft); it just cannot go live until a number is picked.
 */
export function TriggerConnectHint({ kind, gateways }: { kind: GatewayKindId; gateways: readonly GatewayChoice[] | null }) {
  if (kind === 'gateway' || !gateways || gatewaysForKind(kind, gateways).length > 0) return null;
  const channel = CHANNELS.find((c) => c.key === kind);
  return (
    <p className="mt-1 px-1 text-meta text-muted-foreground" data-testid={`flow-card-connect-${kind}`}>
      No {channelNoun(kind)} is connected yet.{' '}
      {channel ? (
        <Link to={channel.setupHref} className="font-medium text-primary underline underline-offset-2" data-testid={`flow-card-connect-link-${kind}`}>
          Connect {channel.label}
        </Link>
      ) : null}
    </p>
  );
}
