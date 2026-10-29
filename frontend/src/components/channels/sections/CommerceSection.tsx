import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { PageFrame } from '@/layouts/PageFrame';
import { useIsHufAdmin } from '@/contexts/PermissionsContext';
import { cn } from '@/lib/utils';
import { getEcosystem, type EcosystemApp } from '@/services/channelsApi';
import { getGateway } from '@/services/gatewayApi';
import { useChannel, useChannelGateway } from '../useChannelGateway';
import { CatalogTab } from '../commerce/CatalogTab';
import { OrdersTab } from '../commerce/OrdersTab';
import { PaymentsTab } from '../commerce/PaymentsTab';
import { CommerceAutomationsTab } from '../commerce/AutomationsTab';
import { FlowsTab } from '../commerce/FlowsTab';

export const COMMERCE_TABS = [
  { key: 'catalog', label: 'Catalog' },
  { key: 'orders', label: 'Orders' },
  { key: 'payments', label: 'Payments' },
  { key: 'automations', label: 'Automations' },
  { key: 'flows', label: 'Flows' },
] as const;
type TabKey = (typeof COMMERCE_TABS)[number]['key'];
export const resolveCommerceTab = (raw?: string): TabKey => COMMERCE_TABS.find((t) => t.key === raw)?.key ?? 'catalog';

export default function CommerceSection() {
  const gw = useChannelGateway();
  const channel = useChannel();
  const isAdmin = useIsHufAdmin();
  const { tab: raw } = useParams<{ tab?: string }>();
  const tab = resolveCommerceTab(raw);
  const [gateway, setGateway] = useState<Record<string, unknown> | null>(null);
  const [erpnext, setErpnext] = useState<EcosystemApp | undefined>();
  const base = gw ? `/channels/${channel}/n/${encodeURIComponent(gw)}/commerce` : '';

  const reload = useCallback(async () => {
    if (!gw) return;
    setGateway(((await getGateway(gw).catch(() => null)) as unknown as Record<string, unknown> | null) ?? null);
  }, [gw]);
  useEffect(() => { setGateway(null); void reload(); }, [reload]);
  useEffect(() => {
    void getEcosystem().then((r) => { if (r.ok) setErpnext(r.data.erpnext); }).catch(() => undefined);
  }, []);

  const props = { gw: gw ?? '', gateway, onSaved: () => void reload() };
  return (
    <PageFrame title="Commerce">
      <div className="flex flex-col gap-4 p-5">
        <nav aria-label="Commerce tabs" className="flex gap-4 overflow-x-auto border-b border-line">
          {COMMERCE_TABS.map((t) => (
            <Link
              key={t.key}
              to={`${base}/${t.key}`}
              aria-current={t.key === tab ? 'page' : undefined}
              className={cn('whitespace-nowrap border-b-2 px-1 pb-2 text-sm', t.key === tab ? 'border-primary font-medium text-ink' : 'border-transparent text-steel hover:text-ink')}
            >
              {t.label}
            </Link>
          ))}
        </nav>
        {!gw && <p className="text-sm text-steel">Pick a gateway to see its commerce settings.</p>}
        {gw && (tab === 'orders' || tab === 'flows') && (tab === 'orders' ? <OrdersTab key={gw} gw={gw} /> : <FlowsTab key={gw} gw={gw} />)}
        {gw && tab !== 'orders' && tab !== 'flows' && !gateway && <p className="text-sm text-steel">Loading...</p>}
        {gw && gateway && tab === 'catalog' && <CatalogTab key={gw} {...props} erpnext={erpnext} isAdmin={isAdmin} />}
        {gw && gateway && tab === 'payments' && <PaymentsTab key={gw} {...props} />}
        {gw && gateway && tab === 'automations' && <CommerceAutomationsTab key={gw} {...props} />}
      </div>
    </PageFrame>
  );
}
