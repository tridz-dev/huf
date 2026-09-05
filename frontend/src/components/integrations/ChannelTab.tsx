import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Check, Copy, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import {
  deleteGateway,
  getAvailableAgents,
  getAvailableFlows,
  getGateways,
  getGatewayReadinessPreview,
  updateGateway,
  type GatewayDoc,
  type GatewayPolicy,
  type GatewayReadinessPreview,
} from '@/services/gatewayApi';
import { getGatewayReadiness } from '@/utils/gatewayReadiness';
import { getGatewayWebhookUrl } from '@/utils/gatewayWebhook';
import { getIntegrationSetting, setupTelegramWebhook } from '@/services/integrationApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

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
  const [copied, setCopied] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [serverReadiness, setReadiness] = useState<GatewayReadinessPreview | null>(null);
  const [readinessLoading, setReadinessLoading] = useState(false);
  // CL-04: Telegram used to have its own separate tab (TelegramTab.tsx) duplicating
  // most of this tab with different field names (telegram_agent instead of
  // default_agent/default_flow) and its own webhook flow. That tab is now removed;
  // its one genuinely provider-specific piece -- the "Setup Webhook" convenience
  // button, which calls Telegram's setWebhook via the Integration Settings record --
  // lives here instead, gated on provider === 'Telegram'.
  const [telegramWebhook, setTelegramWebhook] = useState<{
    url?: string;
    status?: string;
    lastSetup?: string;
  }>({});
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
      setGateway(linked);
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
    } catch (error) {
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
        default_target_type: gateway.default_target_type,
        default_agent: gateway.default_agent || '',
        default_flow: gateway.default_flow || '',
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

  const handleCopyWebhook = () => {
    if (!gateway) return;
    navigator.clipboard.writeText(getGatewayWebhookUrl(gateway.name, gateway.provider));
    setCopied(true);
    toast.success('Webhook URL copied');
    setTimeout(() => setCopied(false), 2000);
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
          messages. Create a gateway for this channel from the Gateways page and connect it to
          these credentials.
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
  const blockingCount = serverReadiness ? serverReadiness.blocking_count : localReadiness.blockingCount;
  const outstandingItems = serverReadiness
    ? serverReadiness.checks.filter((item) => !item.done)
    : localReadiness.items.filter((item) => !item.done && item.id !== 'receiving-traffic');

  return (
    <div className="space-y-6 rounded-lg border p-6">
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

      <div className="space-y-1">
        <label className="text-sm font-medium">Run as user</label>
        <Input
          value={gateway.execution_user || ''}
          onChange={(e) => handleFieldChange({ execution_user: e.target.value })}
          placeholder="e.g. gateway-service@yourcompany.com"
        />
        <p className="text-xs text-muted-foreground">
          Least-privileged user this channel runs agents and flows as. Required while enabled —
          never use an administrator account.
        </p>
      </div>

      <div className="grid gap-3 rounded-lg border p-4">
        <p className="text-sm font-medium">Routing target</p>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Target type</label>
            <Select
              value={gateway.default_target_type || '__none'}
              onValueChange={(v) =>
                handleFieldChange({
                  default_target_type: (v === '__none' ? '' : v) as GatewayDoc['default_target_type'],
                })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none">None</SelectItem>
                <SelectItem value="Agent">Agent</SelectItem>
                <SelectItem value="Flow">Flow</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {gateway.default_target_type === 'Agent' && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Agent</label>
              <Select
                value={gateway.default_agent || '__none'}
                onValueChange={(v) => handleFieldChange({ default_agent: v === '__none' ? '' : v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">Choose an agent…</SelectItem>
                  {agents.map((a) => (
                    <SelectItem key={a.name} value={a.name}>
                      {a.agent_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {gateway.default_target_type === 'Flow' && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Flow</label>
              <Select
                value={gateway.default_flow || '__none'}
                onValueChange={(v) => handleFieldChange({ default_flow: v === '__none' ? '' : v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">Choose a flow…</SelectItem>
                  {flows.map((f) => (
                    <SelectItem key={f.name} value={f.name}>
                      {f.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-sm font-medium">Direct message policy</label>
        <Select
          value={gateway.direct_policy || 'Pairing'}
          onValueChange={(v) => handleFieldChange({ direct_policy: v as GatewayPolicy })}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="Allow list">Allow list — require an approved contact</SelectItem>
            <SelectItem value="Pairing">Pairing — require approval for new senders</SelectItem>
            <SelectItem value="Disabled">Disabled — reject direct messages</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* GW-18: room/group-chat admission policy. These fields already exist on
          the Gateway doctype and were being fetched, but had no editor here. */}
      <div className="grid gap-3 rounded-lg border p-4">
        <p className="text-sm font-medium">Room &amp; group chat admission</p>
        <p className="text-xs text-muted-foreground">
          Controls how this channel admits messages from rooms, channels, or group chats
          (as opposed to one-on-one direct messages, which use the policy above).
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Room policy</label>
            <Select
              value={gateway.room_policy || 'Allow list'}
              onValueChange={(v) => handleFieldChange({ room_policy: v as GatewayPolicy })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Allow list">Allow list — require an approved room</SelectItem>
                <SelectItem value="Disabled">Disabled — reject room messages</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Sender policy within a room</label>
            <Select
              value={gateway.room_sender_policy || 'Allow list'}
              onValueChange={(v) => handleFieldChange({ room_sender_policy: v as GatewayPolicy })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Allow list">Allow list — require an approved sender</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Pairing code lifetime (minutes)</label>
            <Input
              type="number"
              min={1}
              value={gateway.pairing_ttl_minutes ?? 60}
              onChange={(e) =>
                handleFieldChange({ pairing_ttl_minutes: e.target.value ? Number(e.target.value) : undefined })
              }
            />
          </div>
          <div className="flex items-end justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <p className="text-xs font-medium">Require @mention in rooms</p>
              <p className="text-[11px] text-muted-foreground">
                Only respond when the bot is explicitly mentioned
              </p>
            </div>
            <Switch
              checked={Boolean(gateway.mention_required)}
              onCheckedChange={(checked) => handleFieldChange({ mention_required: checked ? 1 : 0 })}
            />
          </div>
        </div>
      </div>

      <div className="space-y-2 rounded-lg border p-4">
        <p className="text-sm font-medium">Inbound webhook URL</p>
        <p className="text-xs text-muted-foreground">
          Paste this URL into the channel provider&apos;s configuration (e.g. Meta Developer
          Console).
        </p>
        <div className="flex items-center gap-2">
          <Input readOnly className="font-mono text-xs" value={getGatewayWebhookUrl(gateway.name, gateway.provider)} />
          <Button type="button" size="sm" variant="outline" onClick={handleCopyWebhook}>
            {copied ? (
              <>
                <Check className="mr-1 h-3.5 w-3.5" /> Copied
              </>
            ) : (
              <>
                <Copy className="mr-1 h-3.5 w-3.5" /> Copy
              </>
            )}
          </Button>
        </div>

        {gateway.provider === 'Telegram' && (
          <div className="mt-3 space-y-2 border-t pt-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <p className="text-xs text-muted-foreground">
                Telegram also needs its webhook registered with the Bot API before it starts
                delivering messages.
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleSetupTelegramWebhook}
                disabled={settingUpWebhook}
              >
                <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', settingUpWebhook && 'animate-spin')} />
                {settingUpWebhook ? 'Setting up...' : 'Setup Webhook'}
              </Button>
            </div>
            {telegramWebhook.status && (
              <Badge
                variant={
                  telegramWebhook.status.toLowerCase().includes('fail') ||
                  telegramWebhook.status.toLowerCase().includes('error')
                    ? 'destructive'
                    : telegramWebhook.status.toLowerCase().includes('configured') ||
                      telegramWebhook.status.toLowerCase().includes('already')
                    ? 'success'
                    : 'secondary'
                }
              >
                {telegramWebhook.status}
              </Badge>
            )}
            {telegramWebhook.lastSetup && (
              <p className="text-xs text-muted-foreground">
                Last setup attempt: {new Date(telegramWebhook.lastSetup).toLocaleString()}
              </p>
            )}
          </div>
        )}
      </div>

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

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this gateway?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the &quot;{gateway.gateway_name}&quot; gateway and stops it from
              receiving messages. The connected credentials are not deleted and can be reused by another
              gateway.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteGateway}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
