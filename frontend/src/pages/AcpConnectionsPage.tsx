import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus, Plug, Settings, Trash2, TestTube, Shield, Terminal } from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, GridView, ItemCard, EmptyState } from '@/components/dashboard';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { AcpConnectionDrawer } from '@/components/acp/AcpConnectionDrawer';
import { AcpPolicyDrawer } from '@/components/acp/AcpPolicyDrawer';
import { usePageData } from '@/hooks/dashboard/usePageData';
import { formatTimeAgo } from '@/utils/time';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type {
  AcpConnection,
  AcpPolicy,
  AcpRegistryEntry,
} from '@/services/acpApi';
import {
  getAcpConnections,
  getAcpRegistryEntries,
  getAcpPolicies,
  deleteAcpConnection,
  deleteAcpPolicy,
  testAcpConnection,
} from '@/services/acpApi';

type AcpTab = 'connections' | 'policies';

const DEFAULT_TAB: AcpTab = 'connections';

function parseTab(value: string | null): AcpTab {
  return value === 'policies' ? 'policies' : DEFAULT_TAB;
}

function healthStatusBadge(status?: AcpConnection['health_status']) {
  switch (status) {
    case 'healthy':
      return { label: 'Connected', variant: 'success' as const };
    case 'degraded':
      return { label: 'Degraded', variant: 'secondary' as const };
    case 'failed':
      return { label: 'Error', variant: 'destructive' as const };
    default:
      return { label: 'Untested', variant: 'outline' as const };
  }
}

export default function AcpConnectionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = parseTab(searchParams.get('tab'));
  const setActiveTab = (tab: AcpTab) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (tab === DEFAULT_TAB) {
          next.delete('tab');
        } else {
          next.set('tab', tab);
        }
        next.delete('search');
        return next;
      },
      { replace: true }
    );
  };

  const [registryEntries, setRegistryEntries] = useState<AcpRegistryEntry[]>([]);
  const [connections, setConnections] = useState<AcpConnection[]>([]);
  const [policies, setPolicies] = useState<AcpPolicy[]>([]);
  const [loading, setLoading] = useState(true);

  const [connectionDrawerOpen, setConnectionDrawerOpen] = useState(false);
  const [editingConnection, setEditingConnection] = useState<AcpConnection | null>(null);
  const [testingConnection, setTestingConnection] = useState<string | null>(null);

  const [policyDrawerOpen, setPolicyDrawerOpen] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState<AcpPolicy | null>(null);

  const {
    data: filteredConnections,
    search: connectionSearch,
    setSearch: setConnectionSearch,
    loading: searchLoading,
  } = usePageData<AcpConnection>({
    fetchFn: undefined,
    initialData: connections,
    searchFields: ['connection_name', 'last_error'],
  });

  const {
    data: filteredPolicies,
    search: policySearch,
    setSearch: setPolicySearch,
    loading: policySearchLoading,
  } = usePageData<AcpPolicy>({
    fetchFn: undefined,
    initialData: policies,
    searchFields: ['policy_name', 'notes'],
  });

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [connList, registryList, policyList] = await Promise.all([
        getAcpConnections(),
        getAcpRegistryEntries(),
        getAcpPolicies(),
      ]);
      setConnections(connList);
      setRegistryEntries(registryList);
      setPolicies(policyList);
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Could not load ACP data');
    } finally {
      setLoading(false);
    }
  }

  const registryMap = useMemo(
    () => new Map(registryEntries.map((r) => [r.name, r])),
    [registryEntries]
  );

  const handleAddConnection = () => {
    setEditingConnection(null);
    setConnectionDrawerOpen(true);
  };

  const handleEditConnection = (connection: AcpConnection) => {
    setEditingConnection(connection);
    setConnectionDrawerOpen(true);
  };

  const handleConnectionSaved = (saved: AcpConnection) => {
    setConnections((prev) => {
      const exists = prev.find((c) => c.name === saved.name);
      if (exists) {
        return prev.map((c) => (c.name === saved.name ? saved : c));
      }
      return [saved, ...prev];
    });
  };

  const handleDeleteConnection = async (name: string) => {
    if (!confirm('Delete this ACP connection?')) return;
    try {
      await deleteAcpConnection(name);
      setConnections((prev) => prev.filter((c) => c.name !== name));
      toast.success('Connection deleted');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Could not delete connection');
    }
  };

  const handleTestConnectionInline = async (connection: AcpConnection) => {
    setTestingConnection(connection.name);
    try {
      const result = await testAcpConnection(connection.name);
      if (result.ok) {
        toast.success('ACP handshake succeeded', {
          description: result.agent_name || 'Initialize completed',
        });
      } else {
        toast.error('ACP handshake failed', {
          description: result.error || 'Unknown error',
        });
      }
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Connection test failed');
    } finally {
      setTestingConnection(null);
    }
  };

  const handleAddPolicy = () => {
    setEditingPolicy(null);
    setPolicyDrawerOpen(true);
  };

  const handleEditPolicy = (policy: AcpPolicy) => {
    setEditingPolicy(policy);
    setPolicyDrawerOpen(true);
  };

  const handlePolicySaved = (saved: AcpPolicy) => {
    setPolicies((prev) => {
      const exists = prev.find((p) => p.name === saved.name);
      if (exists) {
        return prev.map((p) => (p.name === saved.name ? saved : p));
      }
      return [saved, ...prev];
    });
  };

  const handleDeletePolicy = async (name: string) => {
    if (!confirm('Delete this remote agent policy?')) return;
    try {
      await deleteAcpPolicy(name);
      setPolicies((prev) => prev.filter((p) => p.name !== name));
      toast.success('Policy deleted');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Could not delete policy');
    }
  };

  const tabBar = (
    <div className="flex items-center gap-1 border-b border-line">
      {[
        { key: 'connections' as const, label: 'Connections' },
        { key: 'policies' as const, label: 'Policies' },
      ].map((tab) => (
        <Button
          key={tab.key}
          type="button"
          variant="ghost"
          onClick={() => setActiveTab(tab.key)}
          className={
            activeTab === tab.key
              ? 'h-auto rounded-none px-3 pb-2.5 text-sm font-medium border-b-2 -mb-px border-primary text-ink transition-colors hover:bg-transparent'
              : 'h-auto rounded-none px-3 pb-2.5 text-sm font-medium border-b-2 -mb-px border-transparent text-steel hover:text-ink transition-colors hover:bg-transparent'
          }
        >
          {tab.label}
        </Button>
      ))}
    </div>
  );

  return (
    <PageFrame
      title="ACP connections"
      badge={<Badge variant="outline">Experimental</Badge>}
      actions={
        <Button size="sm" onClick={activeTab === 'connections' ? handleAddConnection : handleAddPolicy}>
          <Plus className="mr-1.5 h-4 w-4" />
          {activeTab === 'connections' ? 'Add connection' : 'Add policy'}
        </Button>
      }
      filters={tabBar}
    >
      {activeTab === 'connections' ? (
        <>
          <div className="mb-6 rounded-xl border border-line bg-panel p-5 shadow-xs">
            <div className="flex gap-4">
              <div className="rounded-lg bg-primary/10 p-3 h-fit text-primary">
                <Terminal className="h-6 w-6" />
              </div>
              <div className="space-y-2">
                <h2 className="font-display text-base font-semibold text-ink">
                  Agent Connectivity Protocol (ACP) connections
                </h2>
                <p className="max-w-3xl text-sm text-steel leading-relaxed">
                  ACP connections let Huf agents invoke external ACP-compatible agents (such as
                  kimi-code or Zed) over stdio. Each connection reuses an admin-curated command
                  registry entry so only pre-approved binaries and argument shapes can be launched.
                </p>
              </div>
            </div>
          </div>

          <FilterBar
            searchPlaceholder="Search connections…"
            searchValue={connectionSearch}
            onSearchChange={setConnectionSearch}
          />

          <GridView
            items={filteredConnections}
            loading={loading || searchLoading}
            columns={{ sm: 1, md: 2, lg: 3 }}
            emptyState={
              <EmptyState
                variant="create"
                icon={Plug}
                title="No ACP connections"
                description="Add an ACP connection to let agents call external agents as tools."
                action={{ label: 'Add connection', onClick: handleAddConnection }}
              />
            }
            renderItem={(connection) => {
              const registry = registryMap.get(connection.acp_registry_entry || '');
              const status = healthStatusBadge(connection.health_status);
              return (
                <ItemCard
                  title={connection.connection_name}
                  description={registry ? `${registry.binary_path}` : 'No registry entry'}
                  cornerBadge={
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-background border border-line shadow-2xs">
                      <Terminal className="h-4 w-4 text-steel" />
                    </div>
                  }
                  status={status}
                  metadata={[
                    { label: 'Registry', value: registry?.registry_name || '—' },
                    {
                      label: 'Last checked',
                      value: connection.last_health_check
                        ? formatTimeAgo(connection.last_health_check)
                        : 'Never',
                    },
                    { label: 'Protocol', value: 'ACP (stdio)' },
                  ]}
                  actions={[
                    {
                      icon: TestTube,
                      label: 'Test connection',
                      onClick: () => handleTestConnectionInline(connection),
                      variant: 'ghost',
                    },
                    {
                      icon: Settings,
                      label: 'Configure',
                      onClick: () => handleEditConnection(connection),
                      variant: 'ghost',
                    },
                  ]}
                  menuActions={[
                    {
                      icon: Trash2,
                      label: 'Delete',
                      onClick: () => handleDeleteConnection(connection.name),
                      variant: 'destructive',
                    },
                  ]}
                  footer={
                    connection.last_error ? (
                      <div className="text-[11px] text-destructive line-clamp-1">
                        {connection.last_error}
                      </div>
                    ) : undefined
                  }
                  onClick={() => handleEditConnection(connection)}
                  className={testingConnection === connection.name ? 'opacity-70' : undefined}
                />
              );
            }}
            keyExtractor={(connection) => connection.name}
          />
        </>
      ) : (
        <>
          <div className="mb-6 rounded-xl border border-line bg-panel p-5 shadow-xs">
            <div className="flex gap-4">
              <div className="rounded-lg bg-primary/10 p-3 h-fit text-primary">
                <Shield className="h-6 w-6" />
              </div>
              <div className="space-y-2">
                <h2 className="font-display text-base font-semibold text-ink">Remote agent policies</h2>
                <p className="max-w-3xl text-sm text-steel leading-relaxed">
                  Policies control which callers (API keys, remote connections, or users) can reach
                  which Huf agents through ACP. They are evaluated when an external ACP server
                  requests a new session.
                </p>
              </div>
            </div>
          </div>

          <FilterBar
            searchPlaceholder="Search policies…"
            searchValue={policySearch}
            onSearchChange={setPolicySearch}
          />

          <GridView
            items={filteredPolicies}
            loading={loading || policySearchLoading}
            columns={{ sm: 1, md: 2, lg: 3 }}
            emptyState={
              <EmptyState
                variant="create"
                icon={Shield}
                title="No remote agent policies"
                description="Add a policy to enforce caller scope and capability limits for ACP sessions."
                action={{ label: 'Add policy', onClick: handleAddPolicy }}
              />
            }
            renderItem={(policy) => {
              const status =
                policy.enabled === 1
                  ? { label: 'Active', variant: 'success' as const }
                  : { label: 'Disabled', variant: 'secondary' as const };
              return (
                <ItemCard
                  title={policy.policy_name}
                  description={policy.notes || `Caller: ${policy.caller_type}`}
                  cornerBadge={
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-background border border-line shadow-2xs">
                      <Shield className="h-4 w-4 text-steel" />
                    </div>
                  }
                  status={status}
                  metadata={[
                    { label: 'Scope', value: policy.scope_type === 'single_agent' ? 'Single agent' : 'Agent list' },
                    {
                      label: 'Max duration',
                      value: `${policy.max_run_duration_seconds ?? 300}s`,
                    },
                    {
                      label: 'File tools',
                      value: policy.allow_file_tools === 1 ? 'Allowed' : 'Blocked',
                    },
                    {
                      label: 'Shell tools',
                      value: policy.allow_shell_tools === 1 ? 'Allowed' : 'Blocked',
                    },
                  ]}
                  actions={[
                    {
                      icon: Settings,
                      label: 'Configure',
                      onClick: () => handleEditPolicy(policy),
                      variant: 'ghost',
                    },
                  ]}
                  menuActions={[
                    {
                      icon: Trash2,
                      label: 'Delete',
                      onClick: () => handleDeletePolicy(policy.name),
                      variant: 'destructive',
                    },
                  ]}
                  onClick={() => handleEditPolicy(policy)}
                />
              );
            }}
            keyExtractor={(policy) => policy.name}
          />
        </>
      )}

      <AcpConnectionDrawer
        open={connectionDrawerOpen}
        onOpenChange={setConnectionDrawerOpen}
        connection={editingConnection}
        registryEntries={registryEntries}
        onSaved={handleConnectionSaved}
      />

      <AcpPolicyDrawer
        open={policyDrawerOpen}
        onOpenChange={setPolicyDrawerOpen}
        policy={editingPolicy}
        onSaved={handlePolicySaved}
      />
    </PageFrame>
  );
}
