import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { healthLabel, type HealthState } from '@/services/whatsappHealthApi';
import { listConversations, type ConversationStatus } from '@/services/channelsApi';
import { channelMeta, gatewayDetailHref } from '../channelsMeta';
import { useChannel } from '../useChannelGateway';
import { useGatewaySummary } from '../useGatewaySummary';

const PILL: Record<string, 'pill-success' | 'pill-warning' | 'pill-danger' | 'pill-neutral'> = {
  healthy: 'pill-success',
  degraded: 'pill-warning',
  blocked: 'pill-danger',
  not_set_up: 'pill-neutral',
  disabled: 'pill-neutral',
};

type Count = { n: number; capped: boolean } | null;

async function countStatus(gateway: string, status?: ConversationStatus): Promise<Count> {
  const res = await listConversations(gateway, { status, limit: 100 });
  return res.ok ? { n: res.data.items.length, capped: res.data.has_more } : null;
}
const fmt = (c: Count | undefined) => (c ? `${c.n}${c.capped ? '+' : ''}` : '—');

/** Home for Telegram/Slack/Teams gateways: health from the channel summary plus conversation counters. */
export function ChannelHome({ gateway }: { gateway: string }) {
  const channel = channelMeta(useChannel());
  const { gateways, loading } = useGatewaySummary(channel.key);
  const gw = gateways.find((g) => g.name === gateway);
  const [counts, setCounts] = useState<Record<string, Count>>({});

  useEffect(() => {
    let live = true;
    void Promise.all([countStatus(gateway), countStatus(gateway, 'ai'), countStatus(gateway, 'handed_off')]).then(
      ([all, ai, handed]) => live && setCounts({ all, ai, handed })
    );
    return () => {
      live = false;
    };
  }, [gateway]);

  const stat = (label: string, value: string) => (
    <div className="rounded border border-line px-3 py-2" key={label}>
      <dd className="text-lg font-medium text-ink" data-testid={`counter-${label}`}>{value}</dd>
      <dt className="text-xs text-steel">{label}</dt>
    </div>
  );

  return (
    <div className="space-y-4 p-5">
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
          <div className="space-y-1">
            <div className="text-sm font-medium text-ink">{gateway}</div>
            <div className="flex items-center gap-2 text-xs text-steel">
              {loading ? (
                <span role="status">Loading...</span>
              ) : gw ? (
                <>
                  {gw.health && (
                    <Badge variant={PILL[gw.health] ?? 'pill-neutral'}>{healthLabel(gw.health as HealthState)}</Badge>
                  )}
                  <span>{gw.enabled ? 'Enabled' : 'Turned off'}</span>
                </>
              ) : (
                <span role="alert">{channel.label} {channel.nounSingular} not found</span>
              )}
            </div>
          </div>
          <Button asChild size="sm" variant="outline">
            <Link to={gatewayDetailHref(gateway)}>Manage connection</Link>
          </Button>
        </CardContent>
      </Card>
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Counters">
        {stat('Conversations', fmt(counts.all))}
        {stat('AI-resolved', fmt(counts.ai))}
        {stat('Handed off', fmt(counts.handed))}
      </dl>
    </div>
  );
}
