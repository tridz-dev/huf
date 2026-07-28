import { FormEvent, useEffect, useState } from 'react';
import {
  Check,
  Copy,
  Link2,
  Plus,
  Settings,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react';
import { PageLayout, GridView, ItemCard } from '@/components/dashboard';
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
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { Button } from '@/components/ui/button';
import { getProviderBrandIcon } from '@/components/common/BrandIcons';
import { IntegrationSettingsProvider } from '@/contexts/IntegrationSettingsContext';
import { IntegrationSettingsListingPage } from './IntegrationSettingsListingPage';
import { IntegrationSettingsHeaderActions } from '@/components/integrations/IntegrationSettingsHeaderActions';
import { cn } from '@/lib/utils';

type GatewaysTab = 'gateways' | 'credentials';

const providerNames: Record<GatewayProvider, string> = {
  WhatsApp: 'WhatsApp Business Number',
  Messenger: 'Facebook Messenger Page',
  Instagram: 'Instagram Direct Account',
  Telegram: 'Telegram Bot',
  Slack: 'Slack Workspace',
  Discord: 'Discord Server',
  Email: 'Shared Email Inbox',
  SMS: 'Twilio / SMS Number',
  'Google Chat': 'Google Workspace Chat',
  'Microsoft Teams': 'MS Teams Channel',
  VK: 'VK Community',
  WeCom: 'WeCom Work Account',
};

const uiProviders: GatewayProvider[] = [
  'WhatsApp',
  'Messenger',
  'Instagram',
  'Telegram',
  'Slack',
  'Discord',
  'Email',
  'SMS',
  'Google Chat',
  'Microsoft Teams',
  'VK',
  'WeCom',
];

export default function GatewaysPage() {
  const [activeTab, setActiveTab] = useState<GatewaysTab>('gateways');
  const [catalogOpenKey, setCatalogOpenKey] = useState(0);
  const [gateways, setGateways] = useState<GatewayDoc[]>([]);
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

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [gwList, agentList, flowList] = await Promise.all([
        getGateways(),
        getAvailableAgents(),
        getAvailableFlows(),
      ]);
      setGateways(gwList);
      setAgents(agentList);
      setFlows(flowList);
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
        is_enabled: 1,
        direct_policy: 'Allow list',
      })) as GatewayDoc;
      setGateways((current) => [created, ...current]);
      setGatewayName('');
      setShowSetup(false);
      // Open configuration modal immediately for the new gateway
      setEditingGateway(created);
    } catch {
      setError('Could not create the gateway. Please ensure the name is unique.');
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
    } catch {
      setError('Failed to save gateway configuration.');
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
    return `${host}/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway=${encodeURIComponent(gwName)}`;
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
          { key: 'credentials' as const, label: 'Channel Credentials' },
        ]
      ).map((tab) => (
        <button
          key={tab.key}
          type="button"
          onClick={() => setActiveTab(tab.key)}
          className={cn(
            'px-3 pb-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
            activeTab === tab.key
              ? 'border-primary text-ink'
              : 'border-transparent text-steel hover:text-ink'
          )}
        >
          {tab.label}
        </button>
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

  return (
    <PageLayout subtitle="Let people reach Huf from WhatsApp, Messenger, Instagram, Telegram, and Slack — safely with clear AI routing.">
      {tabBar}

      {/* Overview Card */}
      <div className="mb-6 rounded-xl border border-line bg-panel p-5 shadow-xs">
        <div className="flex gap-4">
          <div className="rounded-lg bg-primary/10 p-3 h-fit text-primary">
            <Link2 className="h-6 w-6" />
          </div>
          <div className="space-y-2">
            <h1 className="text-lg font-semibold text-ink">Channel Gateways & Messaging Ingress</h1>
            <p className="max-w-3xl text-sm text-steel leading-relaxed">
              Gateways serve as safe front doors from external messaging channels (WhatsApp, Messenger,
              Instagram, Telegram, Slack, Email) directly into Huf. Incoming messages are verified, checked
              against security admission policies, and routed to your designated Agents or Flows.
            </p>
            <div className="flex items-center gap-2 text-xs font-medium text-steel">
              <ShieldCheck className="h-4 w-4 text-emerald-500" />
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
            Gateway Name
            <input
              className="h-10 rounded-lg border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              value={gatewayName}
              onChange={(e) => setGatewayName(e.target.value)}
              placeholder="e.g. Support Inbox on WhatsApp"
              required
            />
          </label>

          <label className="grid gap-1.5 text-xs font-medium text-ink">
            Channel Provider
            <div className="relative">
              <select
                className="h-10 w-full rounded-lg border border-input bg-background pl-3 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                value={provider}
                onChange={(e) => setProvider(e.target.value as GatewayProvider)}
              >
                {uiProviders.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
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
          <div className="max-w-xl py-12 text-center mx-auto">
            <div className="mb-3 inline-flex rounded-full bg-panel p-4 text-steel border border-line">
              <Link2 className="h-8 w-8 text-steel" />
            </div>
            <p className="mb-1 font-medium text-ink">No gateways configured yet</p>
            <p className="text-xs text-steel leading-relaxed">
              Connect WhatsApp, Facebook Messenger, Instagram Direct, Telegram, or Slack to allow customers and
              team members to trigger AI Agents directly from messaging apps.
            </p>
          </div>
        }
        renderItem={(gateway) => {
          const target =
            gateway.default_target_type === 'Agent'
              ? gateway.default_agent
              : gateway.default_target_type === 'Flow'
              ? gateway.default_flow
              : 'No default route';

          return (
            <ItemCard
              title={gateway.gateway_name}
              cornerBadge={
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-background border border-line shadow-2xs">
                  {getProviderBrandIcon(gateway.provider, 18)}
                </div>
              }
              description={gateway.description || providerNames[gateway.provider] || `${gateway.provider} channel`}
              status={{
                label: gateway.is_enabled ? 'Active' : 'Disabled',
                variant: gateway.is_enabled ? 'default' : 'secondary',
              }}
              metadata={[
                { label: 'Channel', value: gateway.provider },
                { label: 'Access Policy', value: gateway.direct_policy || 'Allow list' },
                { label: 'Route Target', value: target || 'Unassigned' },
              ]}
              actions={[
                {
                  icon: Settings,
                  label: 'Configure Gateway',
                  onClick: () => setEditingGateway(gateway),
                },
              ]}
            />
          );
        }}
        keyExtractor={(gateway) => gateway.name}
      />

      {/* Native In-App Gateway Settings Modal / Drawer */}
      {editingGateway && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
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
              <button
                onClick={() => setEditingGateway(null)}
                className="rounded-lg p-1.5 text-steel hover:bg-paper hover:text-ink transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
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
                  <div className="w-9 h-5 bg-line peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
                </label>
              </div>

              {/* Description */}
              <label className="grid gap-1 text-xs font-medium text-ink">
                Description
                <input
                  className="h-9 rounded-lg border border-input bg-background px-3 text-xs"
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
                    Target Type
                    <select
                      className="h-9 rounded-lg border border-input bg-background px-2.5 text-xs"
                      value={editingGateway.default_target_type || ''}
                      onChange={(e) =>
                        setEditingGateway({
                          ...editingGateway,
                          default_target_type: e.target.value as any,
                        })
                      }
                    >
                      <option value="">None (Disabled)</option>
                      <option value="Agent">Agent</option>
                      <option value="Flow">Flow</option>
                    </select>
                  </label>

                  {editingGateway.default_target_type === 'Agent' && (
                    <label className="grid gap-1 text-xs font-medium text-ink">
                      Select Agent
                      <select
                        className="h-9 rounded-lg border border-input bg-background px-2.5 text-xs"
                        value={editingGateway.default_agent || ''}
                        onChange={(e) =>
                          setEditingGateway({ ...editingGateway, default_agent: e.target.value })
                        }
                      >
                        <option value="">Choose Agent…</option>
                        {agents.map((a) => (
                          <option key={a.name} value={a.name}>
                            {a.agent_name}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}

                  {editingGateway.default_target_type === 'Flow' && (
                    <label className="grid gap-1 text-xs font-medium text-ink">
                      Select Flow
                      <select
                        className="h-9 rounded-lg border border-input bg-background px-2.5 text-xs"
                        value={editingGateway.default_flow || ''}
                        onChange={(e) =>
                          setEditingGateway({ ...editingGateway, default_flow: e.target.value })
                        }
                      >
                        <option value="">Choose Flow…</option>
                        {flows.map((f) => (
                          <option key={f.name} value={f.name}>
                            {f.title}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                </div>
              </div>

              {/* Direct Access Policy */}
              <label className="grid gap-1 text-xs font-medium text-ink">
                Direct Message Security Policy
                <select
                  className="h-9 rounded-lg border border-input bg-background px-3 text-xs"
                  value={editingGateway.direct_policy || 'Allow list'}
                  onChange={(e) =>
                    setEditingGateway({
                      ...editingGateway,
                      direct_policy: e.target.value as GatewayPolicy,
                    })
                  }
                >
                  <option value="Open">Open — Allow anyone to message</option>
                  <option value="Allow list">Allow list — Require approved Gateway Access Entry</option>
                  <option value="Pairing">Pairing — Require pairing request approval</option>
                  <option value="Disabled">Disabled — Reject direct messages</option>
                </select>
              </label>

              {/* Webhook Configuration Section */}
              <div className="rounded-lg border border-line bg-paper p-4 space-y-2">
                <p className="text-xs font-semibold text-ink">Live Inbound Webhook Endpoint</p>
                <p className="text-[11px] text-steel">
                  Copy and paste this Webhook URL into Meta Developer Console or your channel configuration:
                </p>
                <div className="flex items-center gap-2">
                  <input
                    readOnly
                    className="h-8 flex-1 rounded-md border border-input bg-background px-2.5 font-mono text-[11px] text-steel selection:bg-primary/20"
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
                        <Check className="mr-1 h-3.5 w-3.5 text-emerald-500" /> Copied
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
    </PageLayout>
  );
}
