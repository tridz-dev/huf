import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Send } from 'lucide-react';
import { toast } from 'sonner';
import { PageFrame } from '@/layouts/PageFrame';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { LoadError } from '@/components/whatsapp/BridgeUnavailable';
import { OverviewTab } from '@/components/telegram/OverviewTab';
import {
  getTelegramHealth,
  getTelegramOverview,
  listTelegramGateways,
  type TelegramGatewayOption,
  type TelegramHealth,
  type TelegramOverview,
} from '@/services/telegramApi';

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
    if (gateway && gateway !== gatewayParam) setParams({ gateway }, { replace: true });
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
          <Select value={gateway} onValueChange={(g) => setParams({ gateway: g }, { replace: true })}>
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
          <OverviewTab
            health={health}
            overview={overview}
            loading={!health}
            checking={checking}
            onCheck={onCheck}
            onTurnOn={() => window.open(settingsHref, '_blank', 'noopener,noreferrer')}
            settingsHref={settingsHref}
          />
        )}
      </div>
    </PageFrame>
  );
}
