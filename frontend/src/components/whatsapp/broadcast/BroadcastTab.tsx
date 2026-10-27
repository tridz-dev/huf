import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { errorText } from '@/services/whatsappApi';
import { pauseAllBroadcasts } from './broadcastApi';
import { BridgeUnavailable } from '../BridgeUnavailable';
import { BroadcastDetail } from './BroadcastDetail';
import { BroadcastList } from './BroadcastList';
import { BroadcastWizard } from './BroadcastWizard';

type View = { kind: 'list' } | { kind: 'new' } | { kind: 'detail'; name: string };

export function BroadcastTab({ gateway, bridgeAvailable = true }: { gateway: string; bridgeAvailable?: boolean }) {
  const [view, setView] = useState<View>({ kind: 'list' });
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  if (!bridgeAvailable) return <BridgeUnavailable />;

  const stopAll = async () => {
    setBusy(true);
    const res = await pauseAllBroadcasts(gateway);
    setBusy(false);
    setArmed(false);
    if (res.success) { toast.success('All broadcasts on this gateway were paused'); setRefresh((n) => n + 1); }
    else toast.error(errorText(res));
  };

  return (
    <div className="space-y-6">
      {view.kind === 'list' && <BroadcastList gateway={gateway} refreshKey={refresh} onNew={() => setView({ kind: 'new' })} onOpen={(name) => setView({ kind: 'detail', name })} />}
      {view.kind === 'new' && <BroadcastWizard gateway={gateway} onClose={() => setView({ kind: 'list' })} onStarted={(name) => setView({ kind: 'detail', name })} />}
      {view.kind === 'detail' && <BroadcastDetail key={`${view.name}-${refresh}`} name={view.name} onBack={() => setView({ kind: 'list' })} />}

      <section aria-label="Emergency stop" className="rounded-md border border-destructive/50 p-3">
        <h3 className="text-sm font-semibold text-destructive">Emergency stop</h3>
        <p className="mb-2 text-xs text-steel">Immediately pauses every running broadcast on this gateway. You can resume them one by one afterwards.</p>
        {armed ? (
          <div className="flex items-center gap-2">
            <Button variant="destructive" disabled={busy} onClick={() => void stopAll()}>Confirm: stop all broadcasts</Button>
            <Button variant="ghost" onClick={() => setArmed(false)}>Keep running</Button>
          </div>
        ) : (
          <Button variant="destructive" onClick={() => setArmed(true)}>Stop all broadcasts</Button>
        )}
      </section>
    </div>
  );
}
