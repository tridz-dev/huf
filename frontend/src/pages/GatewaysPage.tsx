import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { type ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import {
  AlertTriangle,
  Check,
  Copy,
  KeyRound,
  Link2,
  Network,
  Plus,
  Settings,
  ShieldCheck,
  Trash2,
  UserCheck,
  X,
} from 'lucide-react';
import { PageFrame } from '@/layouts/PageFrame';
import { GridView, ItemCard, EmptyState } from '@/components/dashboard';
import { DataListView } from '@/components/dashboard/DataListView';
import {
  getGateways,
  updateGateway,
  deleteGateway,
  getAvailableAgents,
  getAvailableFlows,
  type GatewayDoc,
  type GatewayProvider,
  type GatewayPolicy,
} from '@/services/gatewayApi';
import {
  listGatewayAccessEntries,
  approveGatewayPairing,
  revokeGatewayAccessEntry,
  type GatewayAccessEntry,
} from '@/services/gatewayAccessApi';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { useUser } from '@/contexts/UserContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getProviderBrandIcon } from '@/components/common/BrandIcons';
import { IntegrationSettingsProvider } from '@/contexts/IntegrationSettingsContext';
import { IntegrationSettingsListingPage } from './IntegrationSettingsListingPage';
import { IntegrationSettingsHeaderActions } from '@/components/integrations/IntegrationSettingsHeaderActions';
import { getIntegrationSettings } from '@/services/integrationApi';
import type { IntegrationSettingsDoc } from '@/types/integration.types';
import { cn } from '@/lib/utils';
import { formatTimeAgo } from '@/utils/time';
import { getGatewayReadiness } from '@/utils/gatewayReadiness';

// Mirrors huf/ai/gateway_adapters/provider_ids.py::provider_to_service_id
// Must stay in sync with the backend canonical transform for all 12 gateway providers.
// Each provider maps to a lowercase service_name with spaces replaced by underscores.
function providerToServiceId(provider: string): string {
  return provider.toLowerCase().replace(/ /g, '_');
}

type GatewaysTab = 'gateways' | 'pending-access' | 'credentials';

const GATEWAYS_TABS: GatewaysTab[] = ['gateways', 'pending-access', 'credentials'];
const DEFAULT_GATEWAYS_TAB: GatewaysTab = 'gateways';

function parseGatewaysTab(value: string | null): GatewaysTab {
  return GATEWAYS_TABS.includes(value as GatewaysTab) ? (value as GatewaysTab) : DEFAULT_GATEWAYS_TAB;
}

const providerNames: Record<GatewayProvider, string> = {
  WhatsApp: 'WhatsApp Business Number',
  Messenger: 'Facebook Messenger Page',
  Instagram: 'Instagram Direct Account',
  Telegram: 'Telegram Bot',
  Slack: 'Slack Workspace',
  Email: 'Shared Email Inbox',
  'Google Chat': 'Google Workspace Chat',
  'Microsoft Teams': 'MS Teams Channel',
};

const uiProviders: GatewayProvider[] = [
  'WhatsApp',
  'Messenger',
  'Instagram',
  'Telegram',
  'Slack',
  'Email',
  'Google Chat',
  'Microsoft Teams',
];

export default function GatewaysPage() {
  const { user } = useUser();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = parseGatewaysTab(searchParams.get('tab'));
  const setActiveTab = (tab: GatewaysTab) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (tab === DEFAULT_GATEWAYS_TAB) {
          next.delete('tab');
        } else {
          next.set('tab', tab);
        }
        return next;
      },
      { replace: true }
    );
  };
  const [catalogOpenKey, setCatalogOpenKey] = useState(0);
  const [gateways, setGateways] = useState<GatewayDoc[]>([]);
  const [integrationSettings, setIntegrationSettings] = useState<IntegrationSettingsDoc[]>([]);
  const [agents, setAgents] = useState<{ name: string; agent_name: string }[]>([]);
  const [flows, setFlows] = useState<{ name: string; title: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Draft Creation State
  const [showSetup, setShowSetup] = useState(false);
  const [creating, setCreating] = useState(false);
  const [gatewayName, setGatewayName] = useState('');
  const [provider, setProvider] = useState<GatewayProvider>('WhatsApp');

  // Edit / Modal State
  const [editingGateway, setEditingGateway] = useState<GatewayDoc | null>(null);
  const [saving, setSaving] = useState(false);
  const [copiedWebhook, setCopiedWebhook] = useState(false);

  // Pending access (pairing approval) state
  const [pendingEntries, setPendingEntries] = useState<GatewayAccessEntry[]>([]);
  const [pendingLoading, setPendingLoading] = useState(true);
  const [pendingGatewayFilter, setPendingGatewayFilter] = useState('all');
  const [approveCodeInput, setApproveCodeInput] = useState('');
  const [approvingCode, setApprovingCode] = useState(false);
  const [rowActionName, setRowActionName] = useState<string | null>(null);

  useEffect(() => {
    loadData();
    loadPendingEntries();
  }, []);

  useEffect(() => {
    loadPendingEntries();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingGatewayFilter]);

  async function loadPendingEntries() {
    setPendingLoading(true);
    try {
      const entries = await listGatewayAccessEntries({
        gateway: pendingGatewayFilter === 'all' ? undefined : pendingGatewayFilter,
        state: 'Pending',
      });
      setPendingEntries(entries);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not load pending access requests.');
    } finally {
      setPendingLoading(false);
    }
  }

  async function handleApproveByCode(event: FormEvent) {
    event.preventDefault();
    const code = approveCodeInput.trim();
    if (!code) return;
    setApprovingCode(true);
    try {
      await approveGatewayPairing(code);
      toast.success(`Approved ${code}. The sender's next message will now go through.`);
      setApproveCodeInput('');
      loadPendingEntries();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `Could not approve ${code}.`);
    } finally {
      setApprovingCode(false);
    }
  }

  async function handleApproveEntry(entry: GatewayAccessEntry) {
    setRowActionName(entry.name);
    try {
      await approveGatewayPairing(entry.pairing_code || entry.name);
      toast.success(`Approved ${entry.display_label || entry.external_id}.`);
      setPendingEntries((prev) => prev.filter((e) => e.name !== entry.name));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not approve this request.');
    } finally {
      setRowActionName(null);
    }
  }

  async function handleRevokeEntry(entry: GatewayAccessEntry) {
    if (!confirm(`Revoke the pairing request from ${entry.display_label || entry.external_id}?`)) return;
    setRowActionName(entry.name);
    try {
      await revokeGatewayAccessEntry(entry.name);
      toast.success('Access request revoked.');
      setPendingEntries((prev) => prev.filter((e) => e.name !== entry.name));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not revoke this request.');
    } finally {
      setRowActionName(null);
    }
  }

  const pendingColumns = useMemo<ColumnDef<GatewayAccessEntry>[]>(
    () => [
      {
        accessorKey: 'display_label',
        header: 'Sender',
        cell: ({ row }) => (
          <span className="text-sm font-medium text-ink">
            {row.original.display_label || `Sender ${row.original.external_id}`}
          </span>
        ),
      },
      {
        accessorKey: 'gateway',
        header: 'Gateway',
        cell: ({ row }) => <span className="text-xs text-steel">{row.original.gateway}</span>,
      },
      {
        accessorKey: 'provider',
        header: 'Channel',
        cell: ({ row }) => <span className="text-xs text-steel">{row.original.provider}</span>,
      },
      {
        accessorKey: 'pairing_code',
        header: 'Pairing code',
        cell: ({ row }) => (
          <span className="font-mono text-xs text-ink">{row.original.pairing_code || '—'}</span>
        ),
      },
      {
        accessorKey: 'creation',
        header: 'Requested',
        cell: ({ row }) => <span className="text-xs text-steel">{formatTimeAgo(row.original.creation)}</span>,
      },
      {
        accessorKey: 'expires_at',
        header: 'Expires',
        cell: ({ row }) => <span className="text-xs text-steel">{formatTimeAgo(row.original.expires_at)}</span>,
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => {
          const entry = row.original;
          const busy = rowActionName === entry.name;
          return (
            <div className="flex items-center justify-end gap-2">
              <Button
                size="sm"
                variant="outline"
                className="h-7 px-2.5 text-xs"
                disabled={busy}
                onClick={() => handleApproveEntry(entry)}
              >
                <UserCheck className="mr-1 h-3.5 w-3.5" /> Approve
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2.5 text-xs text-destructive hover:text-destructive"
                disabled={busy}
                onClick={() => handleRevokeEntry(entry)}
              >
                <Trash2 className="mr-1 h-3.5 w-3.5" /> Revoke
              </Button>
            </div>
          );
        },
      },
    ],
    [rowActionName]
  );

  async function loadData() {
    setLoading(true);
    try {
      const [gwList, agentList, flowList, settingsResponse] = await Promise.all([
        getGateways(),
        getAvailableAgents(),
        getAvailableFlows(),
        getIntegrationSettings(),
      ]);
      setGateways(gwList);
      setAgents(agentList);
      setFlows(flowList);
      setIntegrationSettings(Array.isArray(settingsResponse) ? settingsResponse : settingsResponse.items);
    } catch {
      setError('Could not load gateway configurations.');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateGateway(event: FormEvent) {
    event.preventDefault();
    if (!gatewayName.trim()) return;
    setCreating(true);
    setError('');
    try {
      const created = (await db.createDoc(doctype.Gateway, {
        gateway_name: gatewayName.trim(),
        provider,
        // Every messaging channel needs credentials before it can carry traffic, and
        // Gateway.validate() enforces that for all providers once enabled. So a new
        // gateway always starts disabled and is turned on after credentials are linked.
        // (This used to vary by provider via a hardcoded 4-entry map, which meant the
        // other 8 were created enabled-but-credential-less and failed at runtime.)
        is_enabled: 0,
        // 'Allow list' with zero access entries silently rejects every inbound DM and never
        // generates a pairing request, so a fresh gateway would go totally silent with a
        // permanently empty Pending access tab. 'Pairing' is safe and self-explaining out of
        // the box: the sender gets a code, the admin gets a request to approve. This also
        // matches setup_gateway()'s own default on the backend.
        direct_policy: 'Pairing',
        execution_user: user?.name,
      })) as GatewayDoc;
      setGateways((current) => [created, ...current]);
      setGatewayName('');
      setShowSetup(false);
      // Open configuration modal immediately for the new gateway
      setEditingGateway(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the gateway. Please ensure the name is unique.');
    } finally {
      setCreating(false);
    }
  }

  async function handleSaveEditing() {
    if (!editingGateway) return;
    setSaving(true);
    try {
      const updated = await updateGateway(editingGateway.name, {
        is_enabled: editingGateway.is_enabled,
        execution_user: editingGateway.execution_user || '',
        integration_settings: editingGateway.integration_settings || '',
        description: editingGateway.description || '',
        direct_policy: editingGateway.direct_policy,
        default_target_type: editingGateway.default_target_type,
        default_agent: editingGateway.default_agent || '',
        default_flow: editingGateway.default_flow || '',
      });
      setGateways((prev) =>
        prev.map((gw) => (gw.name === updated.name ? { ...gw, ...updated } : gw))
      );
      setEditingGateway(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save gateway configuration.');
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteGateway(name: string) {
    if (!confirm('Are you sure you want to delete this gateway?')) return;
    try {
      await deleteGateway(name);
      setGateways((prev) => prev.filter((gw) => gw.name !== name));
      if (editingGateway?.name === name) {
        setEditingGateway(null);
      }
    } catch {
      setError('Failed to delete gateway.');
    }
  }

  function getWebhookUrl(gwName: string) {
    const host = window.location.origin;
    return `${host}/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=${encodeURIComponent(gwName)}`;
  }

  function handleCopyWebhook(gwName: string) {
    navigator.clipboard.writeText(getWebhookUrl(gwName));
    setCopiedWebhook(true);
    setTimeout(() => setCopiedWebhook(false), 2000);
  }

  const tabBar = (
    <div className="mb-6 flex items-center gap-1 border-b border-line">
      {(
        [
          { key: 'gateways' as const, label: 'Gateways' },
          { key: 'pending-access' as const, label: 'Pending access', badge: pendingEntries.length },
          { key: 'credentials' as const, label: 'Channel credentials' },
        ]
      ).map((tab) => (
        <Button
          key={tab.key}
          type="button"
          variant="ghost"
          onClick={() => setActiveTab(tab.key)}
          className={cn(
            'h-auto rounded-none px-3 pb-2.5 text-sm font-medium border-b-2 -mb-px transition-colors hover:bg-transparent',
            activeTab === tab.key
              ? 'border-primary text-ink'
              : 'border-transparent text-steel hover:text-ink'
          )}
        >
          <span className="flex items-center gap-1.5">
            {tab.label}
            {'badge' in tab && (tab.badge ?? 0) > 0 && (
              <Badge
                variant="destructive"
                className="h-4 min-w-[16px] px-1 py-0 flex items-center justify-center"
              >
                {tab.badge! > 9 ? '9+' : tab.badge}
              </Badge>
            )}
          </span>
        </Button>
      ))}
    </div>
  );

  if (activeTab === 'credentials') {
    return (
      <IntegrationSettingsProvider onAddIntegration={() => setCatalogOpenKey((v) => v + 1)}>
        <div className="flex h-full flex-col">
          <div className="flex items-end justify-between gap-4 px-6 pt-6">
            {tabBar}
            <IntegrationSettingsHeaderActions kind="channels" />
          </div>
          <div className="flex-1 overflow-hidden">
            <IntegrationSettingsListingPage kind="channels" catalogOpenKey={catalogOpenKey} />
          </div>
        </div>
      </IntegrationSettingsProvider>
    );
  }

  if (activeTab === 'pending-access') {
    return (
      <PageFrame title="Gateways">
        {tabBar}

        <form
          className="mb-6 grid gap-3 rounded-xl border border-line bg-panel p-5 shadow-xs sm:grid-cols-[1fr_auto] sm:items-end"
          onSubmit={handleApproveByCode}
        >
          <label className="grid gap-1.5 text-xs font-medium text-ink">
            Approve by pairing code
            <Input
              className="h-10 font-mono text-sm uppercase"
              value={approveCodeInput}
              onChange={(e) => setApproveCodeInput(e.target.value)}
              placeholder="PAIR-XXXX"
            />
            <span className="text-[11px] font-normal text-steel">
              Paste the code the sender shared with you to approve them without finding their row below.
            </span>
          </label>
          <Button type="submit" disabled={approvingCode || !approveCodeInput.trim()} className="h-10">
            <KeyRound className="mr-1.5 h-4 w-4" />
            {approvingCode ? 'Approving…' : 'Approve code'}
          </Button>
        </form>

        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold text-base text-ink">Pending pairing requests</h2>
            <p className="text-xs text-steel">
              Senders who messaged a gateway with a Pairing policy wait here until approved.
            </p>
          </div>
          <label className="grid gap-1 text-xs font-medium text-ink">
            <Select value={pendingGatewayFilter} onValueChange={setPendingGatewayFilter}>
              <SelectTrigger className="h-9 w-[220px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All gateways</SelectItem>
                {gateways.map((gw) => (
                  <SelectItem key={gw.name} value={gw.name}>
                    {gw.gateway_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
        </div>

        <DataListView
          columns={pendingColumns}
          data={pendingEntries}
          loading={pendingLoading}
          emptyState={
            <EmptyState
              variant="passive"
              icon={ShieldCheck}
              title="No pending access requests"
              description="When someone DMs a Pairing-policy gateway, their request will show up here for approval."
            />
          }
        />
      </PageFrame>
    );
  }

  return (
    <PageFrame title="Gateways">
      {tabBar}

      {/* Overview Card */}
      <div className="mb-6 rounded-xl border border-line bg-panel p-5 shadow-xs">
        <div className="flex gap-4">
          <div className="rounded-lg bg-primary/10 p-3 h-fit text-primary">
            <Link2 className="h-6 w-6" />
          </div>
          <div className="space-y-2">
            <h2 className="font-display text-base font-semibold text-ink">Channel gateways &amp; messaging ingress</h2>
            <p className="max-w-3xl text-sm text-steel leading-relaxed">
              Gateways serve as safe front doors from external messaging channels (WhatsApp, Messenger,
              Instagram, Telegram, Slack, Email) directly into Huf. Incoming messages are verified, checked
              against security admission policies, and routed to your designated Agents or Flows.
            </p>
            <div className="flex items-center gap-2 text-xs font-medium text-steel">
              <ShieldCheck className="h-4 w-4 text-good" />
              Live webhooks automatically authenticate signatures and enforce allowlists before executing AI tasks.
            </div>
          </div>
        </div>
      </div>

      {/* Header & Add Button */}
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold text-base text-ink">Active Gateways</h2>
          <p className="text-xs text-steel">Configure routing targets, access control, and webhooks in real time.</p>
        </div>
        <Button size="sm" onClick={() => setShowSetup((v) => !v)}>
          {showSetup ? (
            <>
              <X className="mr-1.5 h-4 w-4" /> Cancel
            </>
          ) : (
            <>
              <Plus className="mr-1.5 h-4 w-4" /> Add Gateway
            </>
          )}
        </Button>
      </div>

      {/* Quick Add Form */}
      {showSetup && (
        <form
          className="mb-6 grid gap-4 rounded-xl border border-primary/30 bg-panel p-5 shadow-sm md:grid-cols-[1fr_240px_auto] md:items-end"
          onSubmit={handleCreateGateway}
        >
          <label className="grid gap-1.5 text-xs font-medium text-ink">
            Gateway name
            <Input
              className="h-10 text-sm"
              value={gatewayName}
              onChange={(e) => setGatewayName(e.target.value)}
              placeholder="e.g. Support Inbox on WhatsApp"
              required
            />
          </label>

          <label className="grid gap-1.5 text-xs font-medium text-ink">
            Channel provider
            <Select value={provider} onValueChange={(v) => setProvider(v as GatewayProvider)}>
              <SelectTrigger className="h-10 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {uiProviders.map((p) => (
                  <SelectItem key={p} value={p}>
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>

          <Button type="submit" disabled={creating} className="h-10">
            {creating ? 'Creating…' : 'Create & Configure'}
          </Button>
        </form>
      )}

      {error && <p className="mb-4 text-sm text-destructive">{error}</p>}

      {/* Gateway Grid View with Brand Icons */}
      <GridView
        items={gateways}
        loading={loading}
        columns={{ sm: 1, md: 2, lg: 3 }}
        emptyState={
          <EmptyState
            variant="create"
            icon={Network}
            title="No gateways"
            description="Connect WhatsApp, Messenger, Instagram, Telegram, or Slack to let people message your agents."
            action={{ label: 'Add gateway', onClick: () => setShowSetup(true) }}
          />
        }
        renderItem={(gateway) => {
          const target =
            gateway.default_target_type === 'Agent'
              ? gateway.default_agent
              : gateway.default_target_type === 'Flow'
              ? gateway.default_flow
              : 'No default route';

          const readiness = getGatewayReadiness(gateway);
          const outstandingItems = readiness.items.filter((item) => !item.done && item.id !== 'receiving-traffic');

          return (
            <ItemCard
              title={gateway.gateway_name}
              cornerBadge={
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-background border border-line shadow-2xs">
                  {getProviderBrandIcon(gateway.provider, 18)}
                </div>
              }
              description={gateway.description || providerNames[gateway.provider] || `${gateway.provider} channel`}
              status={
                readiness.ready
                  ? { label: 'Active', variant: 'default' }
                  : {
                      // Keep this short: the status slot sits inline beside the card title and
                      // a full sentence here overlaps it. The specifics are listed in the
                      // card footer, so this only needs to signal "not live, N to fix".
                      label: `${readiness.blockingCount} to set up`,
                      variant: 'secondary',
                    }
              }
              metadata={[
                { label: 'Channel', value: gateway.provider },
                { label: 'Access policy', value: gateway.direct_policy || 'Pairing' },
                { label: 'Route target', value: target || 'Unassigned' },
              ]}
              actions={[
                {
                  icon: Settings,
                  label: 'Configure gateway',
                  onClick: () => {
                    if (gateway.integration_settings) {
                      navigate(`/gateways/${encodeURIComponent(gateway.integration_settings)}`);
                    } else {
                      // No linked Integration Settings record yet (credentials not connected) —
                      // fall back to the gateway-level config modal so the user can still reach
                      // enable/route-target/policy settings and get pointed at Channel credentials.
                      setEditingGateway(gateway);
                    }
                  },
                },
              ]}
              footer={
                readiness.ready ? (
                  <div className="flex items-center gap-1.5 text-[11px] text-steel">
                    {gateway.last_error ? (
                      <>
                        <AlertTriangle className="h-3 w-3 shrink-0 text-destructive" />
                        <span className="line-clamp-1 text-destructive">{gateway.last_error}</span>
                      </>
                    ) : (
                      <span>Last event: {formatTimeAgo(gateway.last_event_at)}</span>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-col gap-1">
                    {outstandingItems.map((item) => (
                      <div key={item.id} className="flex items-center gap-1.5 text-[11px] text-steel">
                        <AlertTriangle className="h-3 w-3 shrink-0 text-destructive" />
                        <span className="line-clamp-1">{item.hint || item.label}</span>
                      </div>
                    ))}
                  </div>
                )
              }
            />
          );
        }}
        keyExtractor={(gateway) => gateway.name}
      />

      {/* Native In-App Gateway Settings Modal / Drawer */}
      {editingGateway && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4 backdrop-blur-xs">
          <div className="w-full max-w-xl rounded-2xl border border-line bg-panel p-6 shadow-xl space-y-6 max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-line pb-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-background border border-line shadow-xs">
                  {getProviderBrandIcon(editingGateway.provider, 24)}
                </div>
                <div>
                  <h3 className="text-base font-semibold text-ink">{editingGateway.gateway_name}</h3>
                  <p className="text-xs text-steel">{providerNames[editingGateway.provider] || editingGateway.provider}</p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setEditingGateway(null)}
                className="h-auto w-auto rounded-lg p-1.5 text-steel hover:bg-paper hover:text-ink transition-colors"
              >
                <X className="h-5 w-5" />
              </Button>
            </div>

            {/* Form Fields */}
            <div className="space-y-4">
              {/* Enabled Toggle */}
              <div className="flex items-center justify-between rounded-lg border border-line bg-paper p-3.5">
                <div>
                  <p className="text-xs font-medium text-ink">Gateway Status</p>
                  <p className="text-[11px] text-steel">Receive and process inbound messages from this channel</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    className="sr-only peer"
                    checked={Boolean(editingGateway.is_enabled)}
                    onChange={(e) =>
                      setEditingGateway({ ...editingGateway, is_enabled: e.target.checked ? 1 : 0 })
                    }
                  />
                  <div className="w-9 h-5 bg-line peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-panel after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-panel after:border-line after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-good"></div>
                </label>
              </div>

              {/* Run as user */}
              <label className="grid gap-1 text-xs font-medium text-ink">
                Run as user
                <Input
                  className="h-9 text-xs"
                  value={editingGateway.execution_user || ''}
                  onChange={(e) =>
                    setEditingGateway({ ...editingGateway, execution_user: e.target.value })
                  }
                  placeholder="e.g. gateway-service@yourcompany.com"
                />
                <span className="text-[11px] font-normal text-steel">
                  Least-privileged user this gateway runs Agents/Flows as. Required while
                  enabled — never use Administrator.
                </span>
              </label>

              {/* Connected Integration (credentials) — shown for every provider, since
                  every messaging channel needs credentials before it can be enabled. */}
              {(() => {
                const requiredService = providerToServiceId(editingGateway.provider);
                const matches = integrationSettings.filter((s) => s.service === requiredService);
                return (
                  <label className="grid gap-1 text-xs font-medium text-ink">
                    Connected integration
                    {matches.length > 0 ? (
                      <Select
                        value={editingGateway.integration_settings || '__none'}
                        onValueChange={(v) =>
                          setEditingGateway({
                            ...editingGateway,
                            integration_settings: v === '__none' ? '' : v,
                          })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none">Choose credentials…</SelectItem>
                          {matches.map((s) => (
                            <SelectItem key={s.name} value={s.name}>
                              {s.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <div className="rounded-lg border border-dashed border-line bg-paper p-3 text-[11px] text-steel">
                        No {editingGateway.provider} credentials connected yet.{' '}
                        <Button
                          type="button"
                          variant="link"
                          className="h-auto p-0 font-medium text-primary hover:underline"
                          onClick={() => setActiveTab('credentials')}
                        >
                          Add one in Channel credentials
                        </Button>
                        .
                      </div>
                    )}
                    <span className="text-[11px] font-normal text-steel">
                      {editingGateway.provider} needs a connected integration before it can be enabled.
                    </span>
                  </label>
                );
              })()}

              {/* Description */}
              <label className="grid gap-1 text-xs font-medium text-ink">
                Description
                <Input
                  className="h-9 text-xs"
                  value={editingGateway.description || ''}
                  onChange={(e) => setEditingGateway({ ...editingGateway, description: e.target.value })}
                  placeholder="e.g. Primary WhatsApp channel for sales inquiries"
                />
              </label>

              {/* Routing Target */}
              <div className="grid gap-3 rounded-lg border border-line bg-paper p-4">
                <p className="text-xs font-semibold text-ink">AI Routing Target</p>
                <div className="grid grid-cols-2 gap-3">
                  <label className="grid gap-1 text-xs font-medium text-ink">
                    Target type
                    <Select
                      value={editingGateway.default_target_type || '__none'}
                      onValueChange={(v) =>
                        setEditingGateway({
                          ...editingGateway,
                          default_target_type: (v === '__none' ? '' : v) as any,
                        })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none">None (disabled)</SelectItem>
                        <SelectItem value="Agent">Agent</SelectItem>
                        <SelectItem value="Flow">Flow</SelectItem>
                      </SelectContent>
                    </Select>
                  </label>

                  {editingGateway.default_target_type === 'Agent' && (
                    <label className="grid gap-1 text-xs font-medium text-ink">
                      Select agent
                      <Select
                        value={editingGateway.default_agent || '__none'}
                        onValueChange={(v) =>
                          setEditingGateway({
                            ...editingGateway,
                            default_agent: v === '__none' ? '' : v,
                          })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none">Choose agent…</SelectItem>
                          {agents.map((a) => (
                            <SelectItem key={a.name} value={a.name}>
                              {a.agent_name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </label>
                  )}

                  {editingGateway.default_target_type === 'Flow' && (
                    <label className="grid gap-1 text-xs font-medium text-ink">
                      Select flow
                      <Select
                        value={editingGateway.default_flow || '__none'}
                        onValueChange={(v) =>
                          setEditingGateway({
                            ...editingGateway,
                            default_flow: v === '__none' ? '' : v,
                          })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none">Choose flow…</SelectItem>
                          {flows.map((f) => (
                            <SelectItem key={f.name} value={f.name}>
                              {f.title}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </label>
                  )}
                </div>
              </div>

              {/* Direct Access Policy */}
              <label className="grid gap-1 text-xs font-medium text-ink">
                Direct message security policy
                <Select
                  value={editingGateway.direct_policy || 'Allow list'}
                  onValueChange={(v) =>
                    setEditingGateway({
                      ...editingGateway,
                      direct_policy: v as GatewayPolicy,
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Allow list">Allow list — Require approved Gateway Access Entry</SelectItem>
                    <SelectItem value="Pairing">Pairing — require pairing request approval</SelectItem>
                    <SelectItem value="Disabled">Disabled — reject direct messages</SelectItem>
                  </SelectContent>
                </Select>
              </label>

              {/* Webhook Configuration Section */}
              <div className="rounded-lg border border-line bg-paper p-4 space-y-2">
                <p className="text-xs font-semibold text-ink">Live Inbound Webhook Endpoint</p>
                <p className="text-[11px] text-steel">
                  Copy and paste this Webhook URL into Meta Developer Console or your channel configuration:
                </p>
                <div className="flex items-center gap-2">
                  <Input
                    readOnly
                    className="h-8 flex-1 font-mono text-[11px] text-steel selection:bg-primary/20"
                    value={getWebhookUrl(editingGateway.name)}
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 px-2.5 text-xs"
                    onClick={() => handleCopyWebhook(editingGateway.name)}
                  >
                    {copiedWebhook ? (
                      <>
                        <Check className="mr-1 h-3.5 w-3.5 text-good" /> Copied
                      </>
                    ) : (
                      <>
                        <Copy className="mr-1 h-3.5 w-3.5" /> Copy
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </div>

            {/* Footer Controls */}
            <div className="flex items-center justify-between border-t border-line pt-4">
              <Button
                variant="destructive"
                size="sm"
                className="h-9 text-xs"
                onClick={() => handleDeleteGateway(editingGateway.name)}
              >
                <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Delete Gateway
              </Button>

              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" className="h-9 text-xs" onClick={() => setEditingGateway(null)}>
                  Cancel
                </Button>
                <Button size="sm" className="h-9 text-xs" disabled={saving} onClick={handleSaveEditing}>
                  {saving ? 'Saving…' : 'Save Changes'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </PageFrame>
  );
}
