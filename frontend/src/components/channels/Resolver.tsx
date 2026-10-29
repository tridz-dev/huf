import { Navigate } from 'react-router-dom';
import { PageLoader } from '@/components/PageLoader';
import { getLastGateway } from './useChannelGateway';
import { useGatewaySummary } from './useGatewaySummary';

/** /channels/whatsapp -> last-used or first enabled gateway home; none -> setup. */
export function GatewayResolver() {
  const { gateways, loading } = useGatewaySummary();
  if (loading) return <PageLoader />;
  const last = getLastGateway();
  const target =
    (last && gateways.find((g) => g.name === last && g.enabled)) || gateways.find((g) => g.enabled);
  if (!target) return <Navigate to="/channels/whatsapp/setup" replace />;
  return <Navigate to={`/channels/whatsapp/n/${encodeURIComponent(target.name)}/home`} replace />;
}
