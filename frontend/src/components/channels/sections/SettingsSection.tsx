import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { PageFrame } from '@/layouts/PageFrame';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { channelMeta, gatewayDetailHref } from '../channelsMeta';
import { useChannel, useChannelGateway } from '../useChannelGateway';
import { getGateway } from '@/services/gatewayApi';
import { resolveSection, SETTINGS_SECTIONS, type GatewayFull, type SettingsKey } from '../settings/model';
import {
  AccessPanel, ConnectionPanel, CredentialsPanel, DangerPanel, HoursPanel, PolicyPanel, RepliesPanel, RunAsPanel,
  type PanelProps,
} from '../settings/panels';
import { useSettingsData } from '../settings/useSettingsData';

const PANELS: Record<SettingsKey, (p: PanelProps) => JSX.Element> = {
  connection: ConnectionPanel,
  credentials: CredentialsPanel,
  policy: PolicyPanel,
  access: AccessPanel,
  'run-as': RunAsPanel,
  hours: HoursPanel,
  replies: RepliesPanel,
  danger: DangerPanel,
};

const OTHER_SECTIONS = [
  { key: 'connection', label: 'Connection' },
  { key: 'run-as', label: 'Run-as user' },
  { key: 'hours', label: 'Business hours' },
] as const;

/** Telegram/Slack/Teams: link to the per-provider page plus the channel-agnostic run-as and hours panels. */
function OtherChannelSettings({ gw }: { gw: string | undefined }) {
  const channel = channelMeta(useChannel());
  const { section: raw } = useParams<{ section?: string }>();
  const section = OTHER_SECTIONS.find((s) => s.key === raw)?.key ?? 'connection';
  const [gateway, setGateway] = useState<GatewayFull | null>(null);
  const [error, setError] = useState('');
  const reload = useCallback(async () => {
    if (!gw) return;
    try {
      setGateway(((await getGateway(gw)) as GatewayFull | null) ?? null);
      setError('');
    } catch {
      setError('Could not load this gateway.');
    }
  }, [gw]);
  useEffect(() => {
    setGateway(null);
    void reload();
  }, [reload]);
  const base = gw ? `/channels/${channel.key}/n/${encodeURIComponent(gw)}/settings` : '';
  const panelProps = { gw: gw ?? '', gateway, onSaved: () => void reload() } as unknown as PanelProps;
  return (
    <PageFrame title="Settings">
      <div className="flex flex-col gap-4 p-5 md:flex-row">
        <nav aria-label="Settings sections" className="flex shrink-0 gap-1 overflow-x-auto md:w-48 md:flex-col">
          {OTHER_SECTIONS.map((s) => (
            <Link
              key={s.key}
              to={`${base}/${s.key}`}
              aria-current={s.key === section ? 'page' : undefined}
              className={cn(
                'whitespace-nowrap rounded-md px-3 py-1.5 text-sm',
                s.key === section ? 'bg-muted font-medium text-ink' : 'text-steel hover:text-ink',
              )}
            >
              {s.label}
            </Link>
          ))}
        </nav>
        <div className="min-w-0 flex-1 space-y-3">
          {!gw && <p className="text-sm text-steel">Pick a {channel.nounSingular} to see its settings.</p>}
          {gw && section === 'connection' && (
            <>
              <p className="text-sm text-steel">
                Credentials and the webhook for this {channel.label} {channel.nounSingular} are managed on its connection page.
              </p>
              <Button asChild size="sm" variant="outline">
                <Link to={channel.key === 'telegram' ? channel.setupHref : gatewayDetailHref(gw)}>Manage connection</Link>
              </Button>
            </>
          )}
          {gw && section !== 'connection' && error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          {gw && section !== 'connection' && !error && !gateway && <p className="text-sm text-steel">Loading...</p>}
          {gw && gateway && section === 'run-as' && <RunAsPanel key={gw} {...panelProps} />}
          {gw && gateway && section === 'hours' && <HoursPanel key={gw} {...panelProps} />}
        </div>
      </div>
    </PageFrame>
  );
}

export default function SettingsSection() {
  const gw = useChannelGateway();
  const channel = useChannel();
  if (channel !== 'whatsapp') return <OtherChannelSettings gw={gw} />;
  return <WhatsAppSettings gw={gw} />;
}

function WhatsAppSettings({ gw }: { gw: string | undefined }) {
  const { section: raw } = useParams<{ section?: string }>();
  const section = resolveSection(raw);
  const { status, gateway, error, reload, runTokenCheck, tokenCheck } = useSettingsData(gw);
  const base = gw ? `/channels/whatsapp/n/${encodeURIComponent(gw)}/settings` : '';
  const Panel = PANELS[section];
  const health = status?.gateway;

  return (
    <PageFrame title="Settings">
      <div className="flex flex-col gap-4 p-5 md:flex-row">
        <nav aria-label="Settings sections" className="flex shrink-0 gap-1 overflow-x-auto md:w-48 md:flex-col">
          {SETTINGS_SECTIONS.map((s) => (
            <Link
              key={s.key}
              to={`${base}/${s.key}`}
              aria-current={s.key === section ? 'page' : undefined}
              className={cn(
                'whitespace-nowrap rounded-md px-3 py-1.5 text-sm',
                s.key === section ? 'bg-muted font-medium text-ink' : 'text-steel hover:text-ink',
              )}
            >
              {s.label}
            </Link>
          ))}
        </nav>
        <div className="min-w-0 flex-1">
          {!gw && <p className="text-sm text-steel">Pick a number to see its settings.</p>}
          {gw && error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          {gw && !error && !health && <p className="text-sm text-steel">Loading...</p>}
          {gw && health && (
            <Panel
              key={`${gw}:${section}`}
              gw={gw}
              health={tokenCheck ? { ...health, token_check: tokenCheck } : health}
              gateway={gateway}
              accounts={status?.accounts ?? []}
              credentialsHref={`${base}/credentials`}
              onCheckToken={runTokenCheck}
              onSaved={() => void reload()}
            />
          )}
        </div>
      </div>
    </PageFrame>
  );
}
