import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { PageFrame } from '@/layouts/PageFrame';
import { cn } from '@/lib/utils';
import { getAgents } from '@/services/agentApi';
import { getGateway } from '@/services/gatewayApi';
import { listSolutions } from '@/services/solutionsApi';
import { useChannelGateway } from '../useChannelGateway';
import { AgentsTab } from '../automations/AgentsTab';
import { HandoffTab } from '../automations/HandoffTab';
import { RulesTab, type TargetOption } from '../automations/RulesTab';
import { HoursPanel, RunAsPanel, type PanelProps } from '../settings/panels';
import type { GatewayFull } from '../settings/model';

export const AUTOMATION_TABS = [
  { key: 'agents', label: 'Agents & Solutions' },
  { key: 'rules', label: 'Routing rules' },
  { key: 'hours', label: 'Business hours' },
  { key: 'handoff', label: 'Handoff rules' },
  { key: 'run-as', label: 'Run-as user' },
] as const;
type TabKey = (typeof AUTOMATION_TABS)[number]['key'];

export const resolveTab = (raw: string | undefined): TabKey =>
  AUTOMATION_TABS.find((t) => t.key === raw)?.key ?? 'agents';

export default function AutomationsSection() {
  const gw = useChannelGateway();
  const { tab: raw } = useParams<{ tab?: string }>();
  const tab = resolveTab(raw);
  const [gateway, setGateway] = useState<GatewayFull | null>(null);
  const [solutions, setSolutions] = useState<TargetOption[]>([]);
  const [agents, setAgents] = useState<TargetOption[]>([]);
  const base = gw ? `/channels/whatsapp/n/${encodeURIComponent(gw)}/automations` : '';

  const reload = useCallback(async () => {
    if (!gw) return;
    setGateway(((await getGateway(gw).catch(() => null)) as GatewayFull | null) ?? null);
  }, [gw]);
  useEffect(() => { setGateway(null); void reload(); }, [reload]);
  useEffect(() => {
    void listSolutions().then((l) => setSolutions(l.map((s) => ({ value: s.name, label: s.title })))).catch(() => undefined);
    void getAgents().then((l) => {
      const list = Array.isArray(l) ? l : l.items ?? [];
      setAgents(list.map((a) => ({ value: a.name, label: a.agent_name || a.name })));
    }).catch(() => undefined);
  }, []);

  const panelProps = { gw: gw ?? '', gateway, onSaved: () => void reload() } as unknown as PanelProps;

  return (
    <PageFrame title="Automations">
      <div className="flex flex-col gap-4 p-5">
        <nav aria-label="Automation tabs" className="flex gap-4 overflow-x-auto border-b border-line">
          {TAB_LINKS(base, tab)}
        </nav>
        {!gw && <p className="text-sm text-steel">Pick a number to see its automations.</p>}
        {gw && tab === 'agents' && <AgentsTab gw={gw} />}
        {gw && tab === 'rules' && <RulesTab gw={gw} solutions={solutions} agents={agents} />}
        {gw && tab !== 'agents' && tab !== 'rules' && !gateway && <p className="text-sm text-steel">Loading...</p>}
        {gw && gateway && tab === 'hours' && <HoursPanel key={gw} {...panelProps} />}
        {gw && gateway && tab === 'handoff' && <HandoffTab key={gw} gw={gw} gateway={gateway as never} onSaved={() => void reload()} />}
        {gw && gateway && tab === 'run-as' && <RunAsPanel key={gw} {...panelProps} />}
      </div>
    </PageFrame>
  );
}

function TAB_LINKS(base: string, tab: TabKey) {
  return AUTOMATION_TABS.map((t) => (
    <Link
      key={t.key}
      to={`${base}/${t.key}`}
      aria-current={t.key === tab ? 'page' : undefined}
      className={cn(
        'whitespace-nowrap border-b-2 px-1 pb-2 text-sm',
        t.key === tab ? 'border-primary font-medium text-ink' : 'border-transparent text-steel hover:text-ink',
      )}
    >
      {t.label}
    </Link>
  ));
}
