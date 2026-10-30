import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { useIsHufAdmin } from '@/contexts/PermissionsContext';
import { getEcosystem, type Ecosystem } from '@/services/channels/channelsApi';
import { CARDS, ConnectionCard, LmsCard, RavanCard } from '../connections/ConnectionCards';

export default function ConnectionsSection() {
  const isAdmin = useIsHufAdmin();
  const [eco, setEco] = useState<Ecosystem | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    void getEcosystem().then((res) => {
      if (!live) return;
      if (res.ok) setEco(res.data);
      else setError(res.error);
      setLoading(false);
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <PageFrame title="Connections">
      <div className="space-y-3 p-5">
        {loading && (
          <div className="flex items-center gap-2 text-xs text-steel"><Loader2 className="h-4 w-4 animate-spin" /> Detecting apps...</div>
        )}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {!loading && !error && (
          <div className="grid gap-3 md:grid-cols-2">
            {CARDS.map((c) => <ConnectionCard key={c.key} def={c} app={eco?.[c.key]} isAdmin={isAdmin} />)}
            <LmsCard />
            <RavanCard app={eco?.ravan} />
          </div>
        )}
      </div>
    </PageFrame>
  );
}
