import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { errorText, getSetupStatus, isBridgeUnavailable, type SetupStatus } from '@/services/whatsappApi';
import { BridgeUnavailable, LoadError } from '@/components/whatsapp/BridgeUnavailable';
import { SetupTab } from '@/components/whatsapp/SetupTab';
import { TemplatesTab } from '@/components/whatsapp/TemplatesTab';
import { MessageLogTab } from '@/components/whatsapp/MessageLogTab';
import { Badge } from '@/components/ui/badge';

export default function WhatsAppManagePage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'templates' || params.get('tab') === 'setup' ? params.get('tab')! : 'messages';
  const gatewayParam = params.get('gateway') || undefined;
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [unavailable, setUnavailable] = useState(false);
  const [selectedGateway, setSelectedGateway] = useState<string | undefined>(gatewayParam);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    const res = await getSetupStatus();
    if (res.success) {
      setStatus(res);
      setUnavailable(!res.bridge_available);
    } else if (isBridgeUnavailable(res)) setUnavailable(true);
    else setError(errorText(res));
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Every tab acts for exactly one gateway: nothing is listed or sent across WhatsApp accounts.
  const gateway = (status?.gateways.find((g) => g.name === selectedGateway) ?? status?.gateways[0])?.name;

  const current = status?.gateways.find((g) => g.name === gateway);

  return (
    <PageFrame
      title="Manage WhatsApp"
      actions={
        status && status.gateways.length > 0 ? (
          <Select value={gateway} onValueChange={setSelectedGateway}>
            <SelectTrigger className="w-56" aria-label="WhatsApp gateway"><SelectValue placeholder="Choose a gateway" /></SelectTrigger>
            <SelectContent>
              {status.gateways.map((g) => <SelectItem key={g.name} value={g.name}>{g.name}</SelectItem>)}
            </SelectContent>
          </Select>
        ) : undefined
      }
    >
      <div className="space-y-3 p-4">
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-steel"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</div>
        ) : error ? (
          <LoadError message={error} onRetry={load} />
        ) : (
          <>
            {current && (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-steel">
                <Badge variant={current.enabled ? 'pill-success' : 'pill-neutral'}>{current.enabled ? 'Enabled' : 'Disabled'}</Badge>
                <span className="font-mono">{current.phone_number_id || 'No phone number set'}</span>
                <span>Replies outside the 24-hour window: {current.fallback_template ? `sent as template ${current.fallback_template}` : 'no fallback template, so they fail'}</span>
              </div>
            )}
            <Tabs value={tab} onValueChange={(v) => setParams((prev) => { const next = new URLSearchParams(); if (prev.get('gateway')) next.set('gateway', prev.get('gateway')!); next.set('tab', v); return next; }, { replace: true })}>
              <TabsList>
                <TabsTrigger value="messages">Messages</TabsTrigger>
                <TabsTrigger value="templates">Templates</TabsTrigger>
                <TabsTrigger value="setup">Setup</TabsTrigger>
              </TabsList>
              <TabsContent value="messages" className="pt-3">
                <MessageLogTab gateway={gateway} bridgeAvailable={!unavailable} />
              </TabsContent>
              <TabsContent value="templates" className="pt-3">
                {unavailable ? <BridgeUnavailable /> : <TemplatesTab gateway={gateway} />}
              </TabsContent>
              <TabsContent value="setup" className="pt-3">
                {status ? <SetupTab status={status} /> : null}
                {unavailable && <div className="mt-6"><BridgeUnavailable /></div>}
              </TabsContent>
            </Tabs>
          </>
        )}
      </div>
    </PageFrame>
  );
}
