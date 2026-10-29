import { lazy, Suspense } from 'react';
import { Navigate, Outlet, Route, Routes, useParams } from 'react-router-dom';
import { PageLoader } from '@/components/PageLoader';
import { ChannelsLayout } from './ChannelsLayout';
import { isChannelKey } from './channelsMeta';
import { GatewayResolver } from './Resolver';
import { useChannel } from './useChannelGateway';

const Home = lazy(() => import('./sections/HomeSection'));
const Activity = lazy(() => import('./sections/ActivitySection'));
const Broadcasts = lazy(() => import('./sections/BroadcastsSection'));
const Templates = lazy(() => import('./sections/TemplatesSection'));
const Automations = lazy(() => import('./sections/AutomationsSection'));
const Connections = lazy(() => import('./sections/ConnectionsSection'));
const Numbers = lazy(() => import('./sections/NumbersSection'));
const Settings = lazy(() => import('./sections/SettingsSection'));
const Analytics = lazy(() => import('./sections/AnalyticsSection'));
const Setup = lazy(() => import('./sections/SetupSection'));

/** Broadcasts and Templates exist for WhatsApp only; other channels bounce to Home. */
function WhatsAppOnly({ children }: { children: JSX.Element }) {
  const channel = useChannel();
  return channel === 'whatsapp' ? children : <Navigate to="../home" replace />;
}

/** Unknown `:channel` values fall back to WhatsApp. */
function ChannelGuard() {
  const { channel } = useParams<{ channel: string }>();
  return isChannelKey(channel) ? <Outlet /> : <Navigate to="/channels/whatsapp" replace />;
}

/** Nested route tree for `/channels/*` (mounted in App.tsx). */
export function ChannelsRoutes() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route element={<ChannelsLayout />}>
          <Route index element={<Navigate to="whatsapp" replace />} />
          <Route path=":channel" element={<ChannelGuard />}>
            <Route index element={<GatewayResolver />} />
            <Route path="setup" element={<Setup />} />
            <Route path="numbers" element={<Numbers />} />
            <Route path="n/:gw">
              <Route index element={<Navigate to="home" replace />} />
              <Route path="home" element={<Home />} />
              <Route path="activity/:conversationId?" element={<Activity />} />
              <Route path="broadcasts/*" element={<WhatsAppOnly><Broadcasts /></WhatsAppOnly>} />
              <Route path="templates/:name?" element={<WhatsAppOnly><Templates /></WhatsAppOnly>} />
              <Route path="automations/:tab?" element={<Automations />} />
              <Route path="connections" element={<Connections />} />
              <Route path="numbers" element={<Numbers />} />
              <Route path="analytics" element={<Analytics />} />
              <Route path="settings/:section?" element={<Settings />} />
            </Route>
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/channels/whatsapp" replace />} />
      </Routes>
    </Suspense>
  );
}

export default ChannelsRoutes;
