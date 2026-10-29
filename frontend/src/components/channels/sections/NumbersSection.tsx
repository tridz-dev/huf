import { Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { PageFrame } from '@/layouts/PageFrame';
import { healthLabel, type HealthState } from '@/services/whatsappHealthApi';
import { channelMeta } from '../channelsMeta';
import { useChannel } from '../useChannelGateway';
import { useGatewaySummary } from '../useGatewaySummary';

const PILL: Record<string, 'pill-success' | 'pill-warning' | 'pill-danger' | 'pill-neutral'> = {
  healthy: 'pill-success',
  degraded: 'pill-warning',
  blocked: 'pill-danger',
  not_set_up: 'pill-neutral',
  disabled: 'pill-neutral',
};

export default function NumbersSection() {
  const channel = channelMeta(useChannel());
  const { gateways, loading, error } = useGatewaySummary(channel.key);
  const add = (
    <Button asChild size="sm">
      <Link to={channel.setupHref}><Plus className="mr-1 h-4 w-4" />Add {channel.nounSingular}</Link>
    </Button>
  );
  return (
    <PageFrame title={channel.noun} actions={add}>
      <div className="space-y-3 p-5">
        {loading ? (
          <Skeleton className="h-24 w-full" />
        ) : error ? (
          <p role="alert" className="text-sm text-destructive">{error}</p>
        ) : gateways.length === 0 ? (
          <p className="text-sm text-steel">No {channel.label} {channel.noun.toLowerCase()} yet.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {gateways.map((g) => {
              const number = (g as { phone?: string | null }).phone;
              return (
                <Card key={g.name} data-gateway={g.name}>
                  <CardContent className="space-y-2 p-4">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium text-ink">{g.name}</span>
                      {g.health && <Badge variant={PILL[g.health] ?? 'pill-neutral'}>{healthLabel(g.health as HealthState)}</Badge>}
                    </div>
                    {number && <div className="font-mono text-xs text-steel">{number}</div>}
                    <div className="flex flex-wrap items-center gap-2 text-xs text-steel">
                      {g.setup_stage && <Badge variant="chip" size="sm">{g.setup_stage}</Badge>}
                      <span>{g.enabled ? 'Enabled' : 'Turned off'}</span>
                    </div>
                    <Link
                      className="text-xs text-signal-ink underline"
                      to={`/channels/${channel.key}/n/${encodeURIComponent(g.name)}/home`}
                    >
                      Open
                    </Link>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </PageFrame>
  );
}
