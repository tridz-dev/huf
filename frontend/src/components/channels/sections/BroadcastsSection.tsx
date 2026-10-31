import { useEffect, useState } from 'react';
import { Link, Navigate, NavLink, Outlet, Route, Routes, useNavigate, useParams } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { AudiencesPage } from '@/components/whatsapp/audiences/AudiencesPage';
import { BroadcastLimits } from '@/components/whatsapp/broadcast/BroadcastLimits';
import { PageFrame } from '@/layouts/PageFrame';
import { BroadcastDetail } from '@/components/whatsapp/broadcast/BroadcastDetail';
import { BroadcastList } from '@/components/whatsapp/broadcast/BroadcastList';
import { BroadcastWizard } from '@/components/whatsapp/broadcast/BroadcastWizard';
import { EmergencyStop } from '@/components/whatsapp/broadcast/BroadcastTab';
import { getSetupStatus } from '@/services/whatsappHealthApi';
import { useChannelGateway } from '../useChannelGateway';

function DetailRoute() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  return <BroadcastDetail name={decodeURIComponent(id)} onBack={() => navigate('..', { relative: 'path' })} />;
}

const TABS = [
  { to: '/channels/whatsapp/n/:gw/broadcasts', label: 'Broadcasts', end: true },
  { to: '/channels/whatsapp/n/:gw/broadcasts/audiences', label: 'Audiences', end: false },
  { to: '/channels/whatsapp/n/:gw/broadcasts/limits', label: 'Limits', end: false },
];

function TabsLayout({ gateway }: { gateway: string }) {
  return (
    <>
      <nav aria-label="Broadcast tabs" className="flex gap-4 overflow-x-auto border-b border-line">
        {TABS.map((t) => (
          <NavLink
            key={t.label}
            to={t.to.replace(':gw', encodeURIComponent(gateway))}
            end={t.end}
            className={({ isActive }) =>
              cn('whitespace-nowrap border-b-2 px-1 pb-2 text-sm', isActive ? 'border-primary font-medium text-ink' : 'border-transparent text-steel hover:text-ink')
            }
          >
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </>
  );
}

type GatewayCheck = 'loading' | 'ok' | 'missing' | 'error';

/** 'missing' = the lookup worked and the number is not there; 'error' = the lookup itself failed (retry). */
function useGatewayExists(gateway: string): { state: GatewayCheck; retry: () => void } {
  const [state, setState] = useState<GatewayCheck>('loading');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setState((s) => (s === 'ok' && attempt === 0 ? s : 'loading'));
    void getSetupStatus(gateway).then((r) => {
      if (!live) return;
      setState(!r.ok ? 'error' : r.data.gateway ? 'ok' : 'missing');
    });
    return () => {
      live = false;
    };
  }, [gateway, attempt]);
  return { state, retry: () => setAttempt((n) => n + 1) };
}

export function BroadcastsUnavailable() {
  return (
    <div role="status" className="space-y-2 rounded-md border border-line p-6 text-sm">
      <p className="font-medium text-ink">Broadcasts are not available yet</p>
      <p className="text-steel">This number could not be found, so there is nothing to send from.</p>
      <Link className="text-primary underline" to="/channels/whatsapp/setup">Connect a number</Link>
    </div>
  );
}

function BroadcastsLoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="alert" className="space-y-3 rounded-md border border-line p-6 text-sm">
      <p className="text-steel">We couldn't load Broadcasts right now. Check your connection and try again.</p>
      <Button size="sm" variant="outline" onClick={onRetry}>Try again</Button>
    </div>
  );
}

/** `broadcasts/*` — tabs (list + emergency stop, `audiences`, `limits`), `new` wizard, `:id` detail. */
export default function BroadcastsSection() {
  const gateway = useChannelGateway() ?? '';
  const navigate = useNavigate();
  const [refresh, setRefresh] = useState(0);
  const { state: exists, retry } = useGatewayExists(gateway);
  if (exists !== 'ok') {
    return (
      <PageFrame title="Broadcasts">
        {exists === 'missing' && <BroadcastsUnavailable />}
        {exists === 'error' && <BroadcastsLoadError onRetry={retry} />}
        {exists === 'loading' && <p role="status" className="p-5 text-sm text-steel">Loading…</p>}
      </PageFrame>
    );
  }
  return (
    <PageFrame title="Broadcasts">
      <div className="space-y-6">
        <Routes>
          <Route element={<TabsLayout gateway={gateway} />}>
            <Route
              index
              element={
                <>
                  <BroadcastList gateway={gateway} refreshKey={refresh} onNew={() => navigate('new')} onOpen={(n) => navigate(encodeURIComponent(n))} />
                  <EmergencyStop gateway={gateway} onStopped={() => setRefresh((n) => n + 1)} />
                </>
              }
            />
            <Route path="audiences" element={<AudiencesPage gateway={gateway} />} />
            <Route path="limits" element={<BroadcastLimits />} />
          </Route>
          <Route
            path="new"
            element={<BroadcastWizard gateway={gateway} onClose={() => navigate('..', { relative: 'path' })} onStarted={(n) => navigate(`../${encodeURIComponent(n)}`, { relative: 'path' })} />}
          />
          <Route path=":id" element={<DetailRoute />} />
          <Route path="*" element={<Navigate to="." replace />} />
        </Routes>
      </div>
    </PageFrame>
  );
}
