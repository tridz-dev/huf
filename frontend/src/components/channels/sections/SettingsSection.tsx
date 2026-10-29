import { Link, useParams } from 'react-router-dom';
import { PageFrame } from '@/layouts/PageFrame';
import { cn } from '@/lib/utils';
import { useChannelGateway } from '../useChannelGateway';
import { resolveSection, SETTINGS_SECTIONS, type SettingsKey } from '../settings/model';
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

export default function SettingsSection() {
  const gw = useChannelGateway();
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
