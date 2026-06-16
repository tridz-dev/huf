import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getHufApp, type HufAppManifest } from '@/services/appApi';
import AppDashboardShell from '@/components/apps/AppDashboardShell';
import AppListShell from '@/components/apps/AppListShell';
import ChatWindow from '@/components/chat/ChatWindowV2';
import { Loader2 } from 'lucide-react';

export default function AppLaunchPage() {
  const { appId } = useParams<{ appId: string }>();
  const [manifest, setManifest] = useState<HufAppManifest | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (appId) getHufApp(appId).then(setManifest).finally(() => setLoading(false));
  }, [appId]);

  if (loading) return <div className="flex items-center justify-center h-full"><Loader2 className="animate-spin" /></div>;
  if (!manifest) return <div className="p-8 text-muted-foreground">App not found.</div>;

  if (manifest.shell === 'chat') {
    return (
      <div className="h-full">
        <ChatWindow chatId={null} defaultAgentName={manifest.agent.agent_name} />
      </div>
    );
  }
  if (manifest.shell === 'dashboard') return <AppDashboardShell manifest={manifest} />;
  if (manifest.shell === 'list') return <AppListShell manifest={manifest} />;
  return null;
}
