import { useCallback, useEffect, useRef, useState } from 'react';
import { getGateway } from '@/services/gatewayApi';
import { checkToken, getSetupStatus, type SetupStatusResponse, type TokenCheckSummary } from '@/services/whatsappHealthApi';
import type { GatewayFull } from './model';

export function useSettingsData(gw: string | undefined) {
  const [status, setStatus] = useState<SetupStatusResponse | null>(null);
  const [gateway, setGateway] = useState<GatewayFull | null>(null);
  const [error, setError] = useState('');
  const [tokenCheck, setTokenCheck] = useState<TokenCheckSummary | null>(null);
  const req = useRef(0);

  const reload = useCallback(async () => {
    if (!gw) return;
    const id = ++req.current;
    setError('');
    const [s, g] = await Promise.all([
      getSetupStatus(gw),
      getGateway(gw).catch(() => null),
    ]);
    if (id !== req.current) return;
    if (!s.ok || !s.data.gateway) setError(s.ok ? 'Could not load this number.' : s.error);
    else setStatus(s.data);
    setGateway((g as GatewayFull | null) ?? null);
  }, [gw]);

  useEffect(() => {
    setStatus(null);
    setGateway(null);
    void reload();
  }, [reload]);

  const runTokenCheck = useCallback(async (): Promise<TokenCheckSummary> => {
    const res = await checkToken(gw ?? '');
    if (!res.ok) throw new Error(res.error);
    const result = res.data as TokenCheckSummary;
    setTokenCheck(result);
    return result;
  }, [gw]);

  return { status, gateway, error, reload, runTokenCheck, tokenCheck, setGateway };
}
