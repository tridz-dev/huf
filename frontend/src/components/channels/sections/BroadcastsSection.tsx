import { useState } from 'react';
import { Navigate, NavLink, Outlet, Route, Routes, useNavigate, useParams } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { AudiencesPage } from '@/components/whatsapp/audiences/AudiencesPage';
import { BroadcastLimits } from '@/components/whatsapp/broadcast/BroadcastLimits';
import { PageFrame } from '@/layouts/PageFrame';
import { BroadcastDetail } from '@/components/whatsapp/broadcast/BroadcastDetail';
import { BroadcastList } from '@/components/whatsapp/broadcast/BroadcastList';
import { BroadcastWizard } from '@/components/whatsapp/broadcast/BroadcastWizard';
import { EmergencyStop } from '@/components/whatsapp/broadcast/BroadcastTab';
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

/** `broadcasts/*` — tabs (list + emergency stop, `audiences`, `limits`), `new` wizard, `:id` detail. */
export default function BroadcastsSection() {
  const gateway = useChannelGateway() ?? '';
  const navigate = useNavigate();
  const [refresh, setRefresh] = useState(0);
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
