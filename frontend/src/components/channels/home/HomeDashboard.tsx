import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ActivityCard } from '@/components/whatsapp/overview/ActivityCard';
import { reasonMessage } from '@/components/whatsapp/overview/healthCopy';
import { HealthBanner } from '@/components/whatsapp/overview/HealthBanner';
import { TokenCard } from '@/components/whatsapp/overview/TokenCard';
import { listConversations, type ConversationStatus } from '@/services/channels/channelsApi';
import { getNumberSummary } from '@/services/solutionsApi';
import type { NumberSummary } from '@/types/solutions';
import { checkToken, getSetupStatus, type GatewayHealthStatus } from '@/services/whatsappHealthApi';

const COUNT_LIMIT = 100;
const base = (gw: string) => `/channels/whatsapp/n/${encodeURIComponent(gw)}`;

/** Count of conversations in a status, '100+' when capped, '—' when unavailable. */
async function countStatus(gateway: string, status?: ConversationStatus): Promise<{ n: number; capped: boolean } | null> {
  const res = await listConversations(gateway, { status, limit: COUNT_LIMIT });
  return res.ok ? { n: res.data.items.length, capped: res.data.has_more } : null;
}

const fmt = (c: { n: number; capped: boolean } | null | undefined) => (c ? `${c.n}${c.capped ? '+' : ''}` : '—');

function Counter({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-line px-3 py-2">
      <dd className="text-lg font-medium text-ink" data-testid={`counter-${label}`}>{value}</dd>
      <dt className="text-xs text-steel">{label}</dt>
    </div>
  );
}

export function HomeDashboard({ gateway }: { gateway: string }) {
  const [gw, setGw] = useState<GatewayHealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const [numberSummary, setNumberSummary] = useState<NumberSummary | null>(null);
  const [counts, setCounts] = useState<Record<string, { n: number; capped: boolean } | null>>({});

  const load = useCallback(async () => {
    const res = await getSetupStatus(gateway);
    if (res.ok && res.data.gateway) {
      setGw(res.data.gateway);
      setError('');
    } else setError(res.ok ? 'Gateway not found' : res.error);
    setLoading(false);
  }, [gateway]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  useEffect(() => {
    let live = true;
    void Promise.all([countStatus(gateway), countStatus(gateway, 'ai'), countStatus(gateway, 'handed_off')]).then(([all, ai, handed]) => {
      if (live) setCounts({ all, ai, handed });
    });
    return () => {
      live = false;
    };
  }, [gateway]);

  // Solutions data is additive: a failed summary only drops the blame line.
  useEffect(() => {
    let live = true;
    setNumberSummary(null);
    getNumberSummary(gateway).then((s) => { if (live) setNumberSummary(s); }).catch(() => undefined);
    return () => { live = false; };
  }, [gateway]);

  const onCheck = async () => {
    setChecking(true);
    await checkToken(gateway);
    await load();
    setChecking(false);
  };

  const attention = gw ? gw.reasons.map((r) => ({ code: r.code, text: reasonMessage(r, gw.events_24h) })) : [];

  return (
    <div className="space-y-4 p-5">
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <HealthBanner gateway={gw} loading={loading} checking={checking} onCheck={() => void onCheck()} numberSummary={numberSummary} />

      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Counters">
        <Counter label="Conversations" value={fmt(counts.all)} />
        <Counter label="AI-resolved" value={fmt(counts.ai)} />
        <Counter label="Handed off" value={fmt(counts.handed)} />
        <Counter label="Template sends" value="—" />
      </dl>

      {gw && (
        <>
          <div className="grid items-start gap-4 lg:grid-cols-2">
            <TokenCard check={gw.token_check} />
            <ActivityCard
              lastEventAt={gw.last_event_at}
              lastError={gw.last_error}
              events24h={gw.events_24h}
              lastFailedEvent={gw.last_failed_event}
              unroutedPhoneIds={gw.unrouted_phone_ids}
              failedEventHref={(ev) => `${base(gateway)}/activity?event=${encodeURIComponent(ev)}`}
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Needs attention</CardTitle>
            </CardHeader>
            <CardContent>
              {attention.length === 0 ? (
                <p className="text-sm text-steel">Nothing needs attention.</p>
              ) : (
                <ul className="list-disc space-y-1 pl-5 text-sm text-ink">
                  {attention.map((a) => <li key={a.code}>{a.text}</li>)}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      )}

      <div className="flex flex-wrap gap-2" aria-label="Quick actions">
        <Button asChild variant="outline" size="sm"><Link to={`${base(gateway)}/templates`}>Send test from Templates</Link></Button>
        <Button asChild variant="outline" size="sm"><Link to={`${base(gateway)}/broadcasts`}>New broadcast</Link></Button>
        <Button asChild variant="outline" size="sm"><Link to={`${base(gateway)}/automations`}>Open Automations</Link></Button>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        {['Help Desk', 'CRM', 'ERPNext'].map((name) => (
          <Card key={name}>
            <CardHeader>
              <CardTitle className="text-sm">{name}</CardTitle>
              <CardDescription>
                <Link className="text-signal-ink underline" to={`${base(gateway)}/connections`}>Set up in Connections</Link>
              </CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default HomeDashboard;
