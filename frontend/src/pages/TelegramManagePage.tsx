import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Send } from 'lucide-react';
import { toast } from 'sonner';
import { PageFrame } from '@/layouts/PageFrame';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { LoadError } from '@/components/whatsapp/BridgeUnavailable';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { resolveTab, TELEGRAM_TABS } from '@/components/telegram/tabs';
import {
  getTelegramHealth,
  getTelegramOverview,
  listTelegramGateways,
  type TelegramGatewayOption,
  type TelegramHealth,
  type TelegramOverview,
} from '@/services/telegramApi';

const GRANTED = new Set<string>(['gateway_admin']);

function NoGateway() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-3 py-16 text-center">
      <Send className="h-8 w-8 text-steel" aria-hidden />
      <h2 className="text-base font-semibold text-ink">Connect your first Telegram bot</h2>
      <p className="text-sm text-steel">Add a Telegram gateway to see its health and what the bot can do here.</p>
      <Button asChild>
        <Link to="/gateways">Add a Telegram gateway</Link>
      </Button>
    </div>
  );
}

export default function TelegramManagePage() {
  const [params, setParams] = useSearchParams();
  const gatewayParam = params.get('gateway') || undefined;
  // Gateway admins see every tab; a tab's `permission` is checked against this set.
  const tabs = TELEGRAM_TABS.filter((t) => !t.permission || GRANTED.has(t.permission));
  const tab = resolveTab(tabs, params.get('tab')).id;

  const [gateways, setGateways] = useState<TelegramGatewayOption[] | null>(null);
  const [listError, setListError] = useState('');
  const [health, setHealth] = useState<TelegramHealth | null>(null);
  const [overview, setOverview] = useState<TelegramOverview | null>(null);
  const [detailError, setDetailError] = useState('');
  const [checking, setChecking] = useState(false);
  const request = useRef(0);

  const loadList = useCallback(async () => {
    setListError('');
    const res = await listTelegramGateways();
    if (res.ok) setGateways(res.data.gateways ?? []);
    else setListError(res.error);
  }, []);
  useEffect(() => { void loadList(); }, [loadList]);

  const gateway = ((gateways ?? []).find((g) => g.name === gatewayParam) ?? (gateways ?? [])[0])?.name;

  // Keep the resolved gateway in the URL so reloads land on the same one.
  useEffect(() => {
    if (gateway && gateway !== gatewayParam) setParams((p) => { const n = new URLSearchParams(p); n.set('gateway', gateway); return n; }, { replace: true });
  }, [gateway, gatewayParam, setParams]);

  const loadDetail = useCallback(async (name: string) => {
    const id = ++request.current;
    setDetailError('');
    const [h, o] = await Promise.all([getTelegramHealth(name), getTelegramOverview(name)]);
    if (id !== request.current) return;
    if (!h.ok) {
      setDetailError(h.error);
      return;
    }
    setHealth(h.data.gateway);
    setOverview(o.ok ? o.data.gateway : null);
  }, []);
  useEffect(() => {
    setHealth(null);
    setOverview(null);
    if (gateway) void loadDetail(gateway);
  }, [gateway, loadDetail]);

  const onCheck = async () => {
    if (!gateway) return;
    setChecking(true);
    await loadDetail(gateway);
    setChecking(false);
    toast.success('Checked just now.');
  };

  const settingsHref = gateway ? `/app/gateway/${encodeURIComponent(gateway)}` : '';
  const loadingList = !gateways && !listError;

  return (
    <PageFrame
      title="Telegram"
      actions={
        gateways && gateways.length > 0 ? (
          <Select value={gateway} onValueChange={(g) => setParams((p) => { const n = new URLSearchParams(p); n.set('gateway', g); return n; }, { replace: true })}>
            <SelectTrigger className="w-full sm:w-64" aria-label="Telegram gateway">
              <SelectValue placeholder="Choose a gateway" />
            </SelectTrigger>
            <SelectContent>
              {gateways.map((g) => (
                <SelectItem key={g.name} value={g.name}>{g.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : undefined
      }
    >
      <div className="space-y-3 p-4">
        {listError ? (
          <LoadError message={listError} onRetry={loadList} />
        ) : loadingList ? (
          <Skeleton className="h-40" />
        ) : !gateway ? (
          <NoGateway />
        ) : detailError ? (
          <LoadError message={detailError} onRetry={() => loadDetail(gateway)} />
        ) : (
          <Tabs
            value={tab}
            onValueChange={(t) => setParams((p) => { const n = new URLSearchParams(p); n.set('tab', t); return n; }, { replace: true })}
          >
            <TabsList layout="scroll" className="sm:w-auto [&>*]:shrink-0">
              {tabs.map((t) => (
                <TabsTrigger key={t.id} value={t.id}>{t.label}</TabsTrigger>
              ))}
            </TabsList>
            {tabs.map((t) => (
              <TabsContent key={t.id} value={t.id} className="pt-3">
                {t.id === tab && (
                  <t.component
                    gateway={gateway}
                    health={health}
                    overview={overview}
                    loading={!health}
                    checking={checking}
                    onCheck={onCheck}
                    onTurnOn={() => window.open(settingsHref, '_blank', 'noopener,noreferrer')}
                    settingsHref={settingsHref}
                  />
                )}
              </TabsContent>
            ))}
          </Tabs>
        )}
      </div>
    </PageFrame>
  );
}
