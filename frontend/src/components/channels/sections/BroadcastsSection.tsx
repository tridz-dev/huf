import { useState } from 'react';
import { Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom';
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

/** `broadcasts/*` — list + emergency stop, `new` wizard, `:id` detail. */
export default function BroadcastsSection() {
  const gateway = useChannelGateway() ?? '';
  const navigate = useNavigate();
  const [refresh, setRefresh] = useState(0);
  return (
    <PageFrame title="Broadcasts">
      <div className="space-y-6">
        <Routes>
          <Route
            index
            element={
              <>
                <BroadcastList gateway={gateway} refreshKey={refresh} onNew={() => navigate('new')} onOpen={(n) => navigate(encodeURIComponent(n))} />
                <EmergencyStop gateway={gateway} onStopped={() => setRefresh((n) => n + 1)} />
              </>
            }
          />
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
