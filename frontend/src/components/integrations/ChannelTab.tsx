import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, ShieldCheck, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Field } from '@/components/ui/field';
import { Switch } from '@/components/ui/switch';
import {
  deleteGateway,
  getAvailableAgents,
  getAvailableFlows,
  getGateway,
  getGateways,
  getGatewayReadinessPreview,
  updateGateway,
  type GatewayDoc,
  type GatewayReadinessPreview,
  WHATSAPP_GATEWAY_FIELDS,
} from '@/services/gatewayApi';
import { ProviderPanels } from '@/components/gateway/ProviderPanels';
import { CONNECTOR_NEEDED } from '@/components/whatsapp/BridgeUnavailable';
import { getSetupStatus } from '@/services/whatsappHealthApi';
import { getGatewayReadiness } from '@/utils/gatewayReadiness';
import { getIntegrationSetting, setupTelegramWebhook } from '@/services/integrationApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { DeleteGatewayDialog } from './channel/DeleteGatewayDialog';
import { ConnectionStatus } from './channel/ConnectionStatus';
import { SlackPolicySection, slackSaveFields } from './channel/SlackPolicySection';
import { DirectPolicySection } from './channel/DirectPolicySection';
import { RoomPolicySection } from './channel/RoomPolicySection';
import { RoutingTargetSection } from './channel/RoutingTargetSection';
import { TestMessageSection } from './channel/TestMessageSection';
import { WebhookSection, type TelegramWebhookState } from './channel/WebhookSection';

interface ChannelTabProps {
  /** Name of the Integration Settings record this channel's credentials live on. */
  settingId?: string;
  /** True while the Integration Settings record hasn't been saved yet. */
  isNew: boolean;
}

export function ChannelTab({ settingId, isNew }: ChannelTabProps) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [gateway, setGateway] = useState<GatewayDoc | null>(null);
  const [agents, setAgents] = useState<{ name: string; agent_name: string }[]>([]);
  const [flows, setFlows] = useState<{ name: string; title: string }[]>([]);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [serverReadiness, setReadiness] = useState<GatewayReadinessPreview | null>(null);
  const [readinessLoading, setReadinessLoading] = useState(false);
  // WhatsApp: whether the WhatsApp connector app (templates, message history) is installed.
  const [connectorAvailable, setConnectorAvailable] = useState<boolean | null>(null);
  // CL-04: Telegram used to have its own separate tab (TelegramTab.tsx) duplicating
  // most of this tab with different field names (telegram_agent instead of
  // default_agent/default_flow) and its own webhook flow. That tab is now removed;
  // its one genuinely provider-specific piece -- the "Setup Webhook" convenience
  // button, which calls Telegram's setWebhook via the Integration Settings record --
  // lives here instead, gated on provider === 'Telegram'.
  const [telegramWebhook, setTelegramWebhook] = useState<TelegramWebhookState>({});
  const [settingUpWebhook, setSettingUpWebhook] = useState(false);

  const load = useCallback(async () => {
    if (!settingId) return;
    setLoading(true);
    try {
      const [gateways, agentList, flowList] = await Promise.all([
        getGateways(),
        getAvailableAgents(),
        getAvailableFlows(),
      ]);
      const linked = gateways.find((g) => g.integration_settings === settingId) || null;
      // The list only carries summary columns; the editor needs every field.
      setGateway(linked ? await getGateway(linked.name) : null);
      if (linked?.provider === 'WhatsApp') {
        const status = await getSetupStatus();
        setConnectorAvailable(status.ok ? status.data.connector_available : null);
      }
      setAgents(agentList);
      setFlows(flowList);

      if (linked?.provider === 'Telegram') {
        const setting = await getIntegrationSetting(settingId);
        setTelegramWebhook({
          url: setting.telegram_webhook_url,
          status: setting.telegram_webhook_status,
          lastSetup: setting.telegram_last_webhook_setup,
        });
      }
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to load channel settings');
    } finally {
      setLoading(false);
    }
  }, [settingId]);

  const handleSetupTelegramWebhook = async () => {
    if (!settingId) return;
    setSettingUpWebhook(true);
    try {
      const result = await setupTelegramWebhook(settingId);
      toast.success(result.status || 'Webhook setup completed');
      const refreshed = await getIntegrationSetting(settingId);
      setTelegramWebhook({
        url: refreshed.telegram_webhook_url,
        status: refreshed.telegram_webhook_status,
        lastSetup: refreshed.telegram_last_webhook_setup,
      });
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to setup webhook');
    } finally {
      setSettingUpWebhook(false);
    }
  };

  const loadReadiness = useCallback(async (gatewayName: string) => {
    setReadinessLoading(true);
    try {
      const preview = await getGatewayReadinessPreview(gatewayName);
      setReadiness(preview);
    } catch {
      // GW-15: this is a server-verified check on top of the local heuristic
      // below, not a replacement for it -- if the endpoint is unreachable we
      // just fall back to the local, less complete checklist rather than
      // blocking the whole tab on a toast.
      setReadiness(null);
    } finally {
      setReadinessLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isNew) {
      load();
    }
  }, [isNew, load]);

  useEffect(() => {
    if (gateway?.name) {
      loadReadiness(gateway.name);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gateway?.name]);

  const handleFieldChange = (patch: Partial<GatewayDoc>) => {
    setGateway((prev) => (prev ? { ...prev, ...patch } : prev));
  };

  const handleSave = async () => {
    if (!gateway) return;
    setSaving(true);
    try {
      const updated = await updateGateway(gateway.name, {
        is_enabled: gateway.is_enabled,
        execution_user: gateway.execution_user || '',
        direct_policy: gateway.direct_policy,
        room_policy: gateway.room_policy,
        room_sender_policy: gateway.room_sender_policy,
        mention_required: gateway.mention_required,
        pairing_ttl_minutes: gateway.pairing_ttl_minutes,
        pairing_reply_enabled: gateway.pairing_reply_enabled,
        pairing_pending_limit: gateway.pairing_pending_limit,
        pairing_reply_daily_limit: gateway.pairing_reply_daily_limit,
        default_target_type: gateway.default_target_type,
        default_agent: gateway.default_agent || '',
        default_flow: gateway.default_flow || '',
        ...slackSaveFields(gateway),
        ...(gateway.provider === 'WhatsApp'
          ? Object.fromEntries(WHATSAPP_GATEWAY_FIELDS.map((field) => [field, gateway[field] ?? null]))
          : {}),
      });
      setGateway((prev) => (prev ? { ...prev, ...updated } : updated));
      loadReadiness(updated.name);
      toast.success('Channel settings saved');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to save channel settings');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteGateway = async () => {
    if (!gateway) return;
    setDeleting(true);
    try {
      // Deleting the Gateway record is sufficient — it is the side that links to
      // Integration Settings (gateway.integration_settings), not the reverse, so
      // there is no FK ordering issue and the linked credentials are left intact
      // for reuse by another gateway.
      await deleteGateway(gateway.name);
      toast.success('Gateway deleted');
      navigate('/gateways');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to delete gateway');
    } finally {
      setDeleting(false);
      setDeleteDialogOpen(false);
    }
  };

  if (isNew) {
    return (
      <div className="rounded-lg border p-6 text-sm text-muted-foreground">
        Save this channel first, then come back here to configure how it receives messages.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="rounded-lg border p-6 text-sm text-muted-foreground">
        Loading channel settings...
      </div>
    );
  }

  if (!gateway) {
    return (
      <div className="space-y-2 rounded-lg border p-6">
        <h3 className="text-sm font-medium">No gateway configured yet</h3>
        <p className="text-sm text-muted-foreground">
          This channel isn&apos;t connected to a gateway yet, so it can&apos;t receive incoming
          messages. Press Use in agent above to pick the agent that answers it, and a gateway is
          created for you.
        </p>
      </div>
    );
  }

  // GW-15: prefer the server-verified readiness (all 8 Gateway.validate()
  // preconditions) once it has loaded; fall back to the local, 3-check
  // heuristic while that request is in flight or if it fails, so the tab
  // never shows nothing.
  const localReadiness = getGatewayReadiness(gateway);
  const ready = serverReadiness ? serverReadiness.ready : localReadiness.ready;
  const rawBlockingCount = serverReadiness ? serverReadiness.blocking_count : localReadiness.blockingCount;
  // The count can be missing if the server payload shape drifts; derive it from
  // the checks, and hide the banner rather than print "undefined".
  const blockingCount: number | undefined =
    typeof rawBlockingCount === 'number' && Number.isFinite(rawBlockingCount)
      ? rawBlockingCount
      : serverReadiness && Array.isArray(serverReadiness.checks)
        ? serverReadiness.checks.filter((item) => !item.done).length
        : undefined;
  const showReadinessBanner = ready || typeof blockingCount === 'number';
  const outstandingItems = serverReadiness
    ? (serverReadiness.checks ?? []).filter((item) => !item.done)
    : localReadiness.items.filter((item) => !item.done && item.id !== 'receiving-traffic');

  return (
    <div className="space-y-6 rounded-lg border p-6">
      {showReadinessBanner && (
      <Alert variant={ready ? 'success' : 'warning'}>
        {ready ? (
          <ShieldCheck className="h-4 w-4" />
        ) : (
          <AlertTriangle className="h-4 w-4" />
        )}
        <AlertTitle>
          {ready
            ? 'Ready to receive messages'
            : `${blockingCount} thing${blockingCount === 1 ? '' : 's'} left before this channel can receive messages`}
        </AlertTitle>
        {readinessLoading && (
          <AlertDescription className="text-xs text-muted-foreground">
            Verifying against server-side requirements...
          </AlertDescription>
        )}
        {outstandingItems.length > 0 && (
          <AlertDescription>
            <ul className="list-disc space-y-0.5 pl-4">
              {outstandingItems.map((item) => (
                <li key={item.id}>{item.hint || item.label}</li>
              ))}
            </ul>
          </AlertDescription>
        )}
      </Alert>
      )}

      <div className="flex items-center justify-between rounded-lg border p-4">
        <div className="space-y-0.5">
          <p className="text-sm font-medium">Channel enabled</p>
          <p className="text-xs text-muted-foreground">
            Receive and process inbound messages from this channel
          </p>
        </div>
        <Switch
          checked={Boolean(gateway.is_enabled)}
          onCheckedChange={(checked) => handleFieldChange({ is_enabled: checked ? 1 : 0 })}
        />
      </div>

      <Field
        label="Run as user"
        hint="Least-privileged user this channel runs agents and flows as. Required while enabled — never use an administrator account."
      >
        <Input
          value={gateway.execution_user || ''}
          onChange={(e) => handleFieldChange({ execution_user: e.target.value })}
          placeholder="e.g. gateway-service@yourcompany.com"
        />
      </Field>

      <ConnectionStatus gateway={gateway} />

      <RoutingTargetSection gateway={gateway} agents={agents} flows={flows} onChange={handleFieldChange} />

      <DirectPolicySection gateway={gateway} onChange={handleFieldChange} />

      <SlackPolicySection gateway={gateway} onChange={handleFieldChange} />

      {/* GW-18: room/group-chat admission policy. These fields already exist on
          the Gateway doctype and were being fetched, but had no editor here.
          WhatsApp has no rooms, so the block is hidden there. */}
      {gateway.provider !== 'WhatsApp' && (
        <RoomPolicySection gateway={gateway} onChange={handleFieldChange} />
      )}

      {gateway.provider === 'WhatsApp' && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-4 text-xs text-muted-foreground">
            <span>
              {gateway.whatsapp_account ? (
                <>
                  Templates and message history use the WhatsApp account{' '}
                  <span className="font-medium text-foreground">{gateway.whatsapp_account}</span>, kept in step
                  with this channel&apos;s credentials.
                </>
              ) : connectorAvailable === false ? (
                `${CONNECTOR_NEEDED}. Replies, voice notes and the agent work without it.`
              ) : (
                'Save the credentials to link this number to its WhatsApp account for templates and message history.'
              )}
            </span>
            <Button type="button" variant="outline" size="sm" onClick={() => navigate(`/channels/whatsapp/n/${encodeURIComponent(gateway.name)}/settings`)}>
              Manage in Channels
            </Button>
          </div>
        </>
      )}

      <TestMessageSection gateway={gateway} />

      <WebhookSection
        gateway={gateway}
        telegramWebhook={telegramWebhook}
        settingUpWebhook={settingUpWebhook}
        onSetupTelegramWebhook={handleSetupTelegramWebhook}
      />

      <ProviderPanels gateway={gateway} />

      <div className="flex items-center justify-between">
        <Button
          type="button"
          variant="destructive"
          onClick={() => setDeleteDialogOpen(true)}
        >
          <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Delete gateway
        </Button>
        <Button type="button" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save channel settings'}
        </Button>
      </div>

      <DeleteGatewayDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        gatewayName={gateway.gateway_name}
        deleting={deleting}
        onConfirm={handleDeleteGateway}
      />
    </div>
  );
}
