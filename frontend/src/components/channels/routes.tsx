import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { PageLoader } from '@/components/PageLoader';
import { ChannelsLayout } from './ChannelsLayout';
import { GatewayResolver } from './Resolver';

const Home = lazy(() => import('./sections/HomeSection'));
const Activity = lazy(() => import('./sections/ActivitySection'));
const Broadcasts = lazy(() => import('./sections/BroadcastsSection'));
const Templates = lazy(() => import('./sections/TemplatesSection'));
const Automations = lazy(() => import('./sections/AutomationsSection'));
const Connections = lazy(() => import('./sections/ConnectionsSection'));
const Numbers = lazy(() => import('./sections/NumbersSection'));
const Settings = lazy(() => import('./sections/SettingsSection'));
const Setup = lazy(() => import('./sections/SetupSection'));

/** Nested route tree for `/channels/*` (mounted in App.tsx). */
export function ChannelsRoutes() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route element={<ChannelsLayout />}>
          <Route index element={<Navigate to="whatsapp" replace />} />
          <Route path="whatsapp">
            <Route index element={<GatewayResolver />} />
            <Route path="setup" element={<Setup />} />
            <Route path="numbers" element={<Numbers />} />
            <Route path="n/:gw">
              <Route index element={<Navigate to="home" replace />} />
              <Route path="home" element={<Home />} />
              <Route path="activity" element={<Activity />} />
              <Route path="broadcasts/*" element={<Broadcasts />} />
              <Route path="templates/:name?" element={<Templates />} />
              <Route path="automations" element={<Automations />} />
              <Route path="connections" element={<Connections />} />
              <Route path="numbers" element={<Numbers />} />
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
