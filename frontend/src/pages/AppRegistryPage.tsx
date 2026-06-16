import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, ExternalLink } from 'lucide-react';
import { PageLayout } from '@/components/dashboard/layouts/PageLayout';
import { GridView } from '@/components/dashboard/views/GridView';
import { ItemCard } from '@/components/dashboard/cards/ItemCard';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { getHufApps, deleteHufApp, type HufAppSummary } from '@/services/appApi';

export default function AppRegistryPage() {
  const navigate = useNavigate();
  const [apps, setApps] = useState<HufAppSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getHufApps().then(setApps).finally(() => setLoading(false));
  }, []);

  async function handleDelete(appId: string) {
    if (!confirm(`Delete app "${appId}"? The data tables will remain.`)) return;
    try {
      await deleteHufApp(appId);
      setApps(prev => prev.filter(a => a.app_id !== appId));
      toast.success('App deleted');
    } catch {
      // handleFrappeError already toasts
    }
  }

  return (
    <PageLayout
      toolbar={
        <Button onClick={() => navigate('/apps/new')}>
          <Plus className="w-4 h-4 mr-2" /> New App
        </Button>
      }
    >
      <GridView
        items={apps}
        loading={loading}
        keyExtractor={a => a.app_id}
        columns={{ sm: 1, md: 2, lg: 3 }}
        emptyState={
          <div className="text-center py-16 text-muted-foreground">
            <p className="mb-4">No apps yet.</p>
            <Button onClick={() => navigate('/apps/new')}>Build your first app</Button>
          </div>
        }
        renderItem={app => (
          <ItemCard
            key={app.app_id}
            title={app.label}
            description={app.description}
            status={{ label: app.shell, variant: 'secondary' }}
            metadata={[{ label: 'Agent', value: app.agent }]}
            actions={[
              {
                icon: ExternalLink,
                label: 'Launch',
                onClick: () => navigate(`/apps/${app.app_id}`),
              },
            ]}
            menuActions={[
              {
                icon: Trash2,
                label: 'Delete',
                onClick: () => handleDelete(app.app_id),
                variant: 'destructive',
              },
            ]}
            onClick={() => navigate(`/apps/${app.app_id}`)}
          />
        )}
      />
    </PageLayout>
  );
}
