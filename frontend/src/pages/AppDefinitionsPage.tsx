import { useEffect, useState } from 'react';
import { RefreshCw, FolderOpen, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { PageLayout } from '@/components/dashboard';
import { Button } from '@/components/ui/button';
import {
  getAppDiscoveryStatus,
  discoverAppDefinitions,
  rebuildAppDefinitions,
  type AppDiscoveryStatus,
} from '@/services/appDiscoveryApi';

export function AppDefinitionsPage() {
  const [status, setStatus] = useState<AppDiscoveryStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [expandedApp, setExpandedApp] = useState<string | null>(null);

  const loadStatus = async () => {
    setLoading(true);
    try {
      const data = await getAppDiscoveryStatus();
      setStatus(data);
    } catch {
      toast.error('Failed to load app discovery status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleSyncAll = async () => {
    setSyncing('all');
    try {
      const result = await discoverAppDefinitions(null, false);
      toast.success(
        `Synced ${result.total_definitions} definitions from ${result.synced_apps?.length ?? 0} apps`
      );
      if (result.error_count > 0) {
        toast.warning(`${result.error_count} error(s) during sync`, {
          description: result.errors?.[0],
        });
      }
      await loadStatus();
    } catch {
      toast.error('Failed to sync app definitions');
    } finally {
      setSyncing(null);
    }
  };

  const handleSyncApp = async (appName: string) => {
    setSyncing(appName);
    try {
      const result = await discoverAppDefinitions(appName, false);
      toast.success(`Synced ${result.total_definitions} definitions from ${appName}`);
      await loadStatus();
    } catch {
      toast.error(`Failed to sync ${appName}`);
    } finally {
      setSyncing(null);
    }
  };

  const handleRebuild = async () => {
    setSyncing('rebuild');
    try {
      const result = await rebuildAppDefinitions();
      toast.success(`Rebuilt: ${result.total_definitions} definitions synced`);
      await loadStatus();
    } catch {
      toast.error('Failed to rebuild app definitions');
    } finally {
      setSyncing(null);
    }
  };

  return (
    <PageLayout
      subtitle="Discover and sync AI definitions (agents, tools, prompts, etc.) from installed apps via huf/ folder"
      toolbar={
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleSyncAll}
            disabled={!!syncing}
          >
            {syncing === 'all' ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            <span className="ml-2">Sync All</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleRebuild}
            disabled={!!syncing}
          >
            {syncing === 'rebuild' ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            <span className="ml-2">Rebuild</span>
          </Button>
        </div>
      }
    >
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-lg border bg-card p-4">
            <h3 className="font-medium mb-2">App Definitions</h3>
            <p className="text-sm text-muted-foreground mb-4">
              Apps can declare AI capabilities by placing JSON files in <code className="rounded bg-muted px-1">huf/</code> folders.
              Scan runs automatically on migrate; use Sync to refresh manually.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 font-medium">App</th>
                    <th className="text-left py-2 font-medium">huf/ folder</th>
                    <th className="text-left py-2 font-medium">Definitions</th>
                    <th className="text-left py-2 font-medium">Last sync</th>
                    <th className="text-left py-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {status.map((s) => {
                    const count = Object.values(s.definition_counts || {}).reduce((a, b) => a + b, 0);
                    const isExpanded = expandedApp === s.app;
                    return (
                      <tr key={s.app} className="border-b last:border-0">
                        <td className="py-3 font-medium">{s.app}</td>
                        <td className="py-3">
                          {s.has_huf_dir ? (
                            <CheckCircle2 className="h-4 w-4 text-green-600" />
                          ) : (
                            <XCircle className="h-4 w-4 text-muted-foreground" />
                          )}
                        </td>
                        <td className="py-3">
                          {count > 0 ? (
                            <span className="font-mono text-xs">
                              {Object.entries(s.definition_counts || {})
                                .filter(([, v]) => v > 0)
                                .map(([k, v]) => `${k}: ${v}`)
                                .join(', ')}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="py-3 text-muted-foreground">
                          {s.last_sync
                            ? new Date(s.last_sync).toLocaleString()
                            : '—'}
                        </td>
                        <td className="py-3">
                          {s.has_huf_dir && count > 0 && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleSyncApp(s.app)}
                              disabled={!!syncing}
                            >
                              {syncing === s.app ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <RefreshCw className="h-4 w-4" />
                              )}
                              <span className="ml-1">Sync</span>
                            </Button>
                          )}
                          {s.has_huf_dir && (s.files?.length ?? 0) > 0 && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                setExpandedApp(isExpanded ? null : s.app)
                              }
                            >
                              <FolderOpen className="h-4 w-4" />
                              <span className="ml-1">Files</span>
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {expandedApp && (
              <div className="mt-4 p-3 rounded-md bg-muted/50 text-xs font-mono space-y-1">
                {(status.find((s) => s.app === expandedApp)?.files || []).map((f) => (
                  <div key={f}>{f}</div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </PageLayout>
  );
}
