import { useCallback, useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { Button } from '@/components/ui/button';
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '@/components/ui/chart';
import { PageFrame } from '@/layouts/PageFrame';
import { RateCardEditor } from '../analytics/RateCardEditor';
import { useChannelGateway } from '../useChannelGateway';
import { getAnalytics, type Analytics } from '@/services/channels/analyticsApi';

const RANGES = [7, 30, 90] as const;
const chartConfig = {
  inbound: { label: 'Inbound', color: 'var(--signal)' },
  outbound: { label: 'Outbound', color: 'var(--steel)' },
} satisfies ChartConfig;

const iso = (d: Date) => d.toISOString().slice(0, 10);
const pct = (v: number | null) => (v == null ? '—' : `${Math.round(v * 100)}%`);
const dur = (s: number | null) => (s == null ? '—' : s < 90 ? `${Math.round(s)}s` : `${Math.round(s / 60)}m`);

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-line px-3 py-2">
      <dd className="text-lg font-medium text-ink">{value}</dd>
      <dt className="text-xs text-steel">{label}</dt>
    </div>
  );
}

export default function AnalyticsSection() {
  const gateway = useChannelGateway();
  const [days, setDays] = useState<(typeof RANGES)[number]>(30);
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);

  const load = useCallback(async () => {
    if (!gateway) return;
    const to = new Date();
    const from = new Date(to.getTime() - (days - 1) * 86400000);
    const res = await getAnalytics(gateway, iso(from), iso(to));
    if (res.ok) {
      setData(res.data);
      setError('');
    } else setError(res.error);
  }, [gateway, days]);

  useEffect(() => {
    void load();
  }, [load]);

  const range = (
    <div role="group" aria-label="Date range" className="flex gap-1">
      {RANGES.map((d) => (
        <Button key={d} size="sm" variant={days === d ? 'secondary' : 'ghost'} aria-pressed={days === d} onClick={() => setDays(d)}>
          {d}d
        </Button>
      ))}
    </div>
  );

  const f = data?.broadcast_funnel;
  const max = Math.max(1, f?.sent ?? 0);
  const spend = data?.estimated_spend;

  return (
    <PageFrame title="Analytics" actions={range}>
      <div className="space-y-6 p-5">
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {data && (
          <>
            <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Tile label="AI resolution rate" value={pct(data.ai_resolution_rate)} />
              <Tile label="Handoff rate" value={pct(data.handoff_rate)} />
              <Tile label="Median first response" value={dur(data.median_first_response_seconds)} />
              <Tile label="Conversations" value={String(data.volume_by_day.reduce((a, d) => a + d.conversations, 0))} />
            </dl>

            <section aria-label="Message volume">
              <h2 className="mb-2 text-sm font-medium text-ink">Message volume</h2>
              <ChartContainer config={chartConfig} className="aspect-auto h-56 w-full">
                <BarChart data={data.volume_by_day}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(v: string) => v.slice(5)} />
                  <YAxis allowDecimals={false} width={32} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar dataKey="inbound" fill="var(--color-inbound)" radius={2} />
                  <Bar dataKey="outbound" fill="var(--color-outbound)" radius={2} />
                </BarChart>
              </ChartContainer>
            </section>

            <section aria-label="Broadcast funnel">
              <h2 className="mb-2 text-sm font-medium text-ink">Broadcast funnel</h2>
              <ul className="space-y-1.5">
                {(['sent', 'delivered', 'read', 'failed'] as const).map((k) => (
                  <li key={k} className="flex items-center gap-3 text-sm">
                    <span className="w-20 capitalize text-steel">{k}</span>
                    <svg aria-hidden className="h-2 flex-1 overflow-hidden rounded bg-paper-deep" preserveAspectRatio="none">
                      <rect height="100%" width={`${(f![k] / max) * 100}%`} className={k === 'failed' ? 'fill-destructive' : 'fill-signal'} />
                    </svg>
                    <span className="w-12 text-right text-ink">{f![k]}</span>
                  </li>
                ))}
              </ul>
            </section>

            <section aria-label="Template quality">
              <h2 className="mb-2 text-sm font-medium text-ink">Template quality</h2>
              {data.template_quality.length === 0 ? (
                <p className="text-xs text-steel">No templates.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-steel">
                    <tr><th className="py-1">Template</th><th>Quality</th><th>Category</th></tr>
                  </thead>
                  <tbody>
                    {data.template_quality.map((t) => (
                      <tr key={t.name} className="border-t border-line">
                        <td className="py-1 text-ink">{t.name}</td>
                        <td className="text-ink-soft">{t.quality ?? '—'}</td>
                        <td className="text-ink-soft">{t.category ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section aria-label="Estimated spend" className="rounded border border-line p-3">
              <h2 className="text-sm font-medium text-ink">Estimated spend</h2>
              <p className="text-lg font-medium text-ink">
                {spend?.amount == null ? '—' : `${spend.currency ?? ''} ${spend.amount.toFixed(2)}`}
              </p>
              <p className="text-xs text-steel">Estimate — you pay Meta directly. Meta&apos;s invoice is the source of truth.</p>
              {spend?.missing_rates && (
                <p className="text-xs text-warning">Some rates are missing, so no total can be shown.</p>
              )}
              <Button size="sm" variant="link" onClick={() => setEditing((e) => !e)}>
                {editing ? 'Hide rate card' : 'Edit rate card'}
              </Button>
              {editing && <RateCardEditor onSaved={() => void load()} />}
            </section>
          </>
        )}
      </div>
    </PageFrame>
  );
}
