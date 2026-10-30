import { Navigate } from 'react-router-dom';
import { PageLoader } from '@/components/PageLoader';
import { channelMeta } from './channelsMeta';
import { getLastGateway, useChannel } from './useChannelGateway';
import { useGatewaySummary } from './useGatewaySummary';

/** /channels/:channel -> last-used or first enabled gateway home; none -> setup. */
export function GatewayResolver() {
  const channel = useChannel();
  const { gateways, loading } = useGatewaySummary(channel);
  if (loading) return <PageLoader />;
  const last = getLastGateway(channel);
  const target =
    (last && gateways.find((g) => g.name === last && g.enabled)) || gateways.find((g) => g.enabled);
  if (!target) return <Navigate to={`/channels/${channel}/setup`} replace />;
  void channelMeta;
  return <Navigate to={`/channels/${channel}/n/${encodeURIComponent(target.name)}/home`} replace />;
}
