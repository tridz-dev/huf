import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Check, Copy, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
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
  getAvailableAgents,
  getAvailableFlows,
  getGateways,
  updateGateway,
  type GatewayDoc,
  type GatewayPolicy,
} from '@/services/gatewayApi';
import { getGatewayReadiness } from '@/utils/gatewayReadiness';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

interface ChannelTabProps {
  /** Name of the Integration Settings record this channel's credentials live on. */
  settingId?: string;
  /** True while the Integration Settings record hasn't been saved yet. */
  isNew: boolean;
}

function getWebhookUrl(gatewayName: string) {
  const host = window.location.origin;
  return `${host}/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=${encodeURIComponent(gatewayName)}`;
}

export function ChannelTab({ settingId, isNew }: ChannelTabProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [gateway, setGateway] = useState<GatewayDoc | null>(null);
  const [agents, setAgents] = useState<{ name: string; agent_name: string }[]>([]);
  const [flows, setFlows] = useState<{ name: string; title: string }[]>([]);
  const [copied, setCopied] = useState(false);

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
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to load channel settings');
    } finally {
      setLoading(false);
    }
  }, [settingId]);

  useEffect(() => {
    if (!isNew) {
      load();
    }
  }, [isNew, load]);

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
        default_target_type: gateway.default_target_type,
        default_agent: gateway.default_agent || '',
        default_flow: gateway.default_flow || '',
      });
      setGateway((prev) => (prev ? { ...prev, ...updated } : updated));
      toast.success('Channel settings saved');
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to save channel settings');
    } finally {
      setSaving(false);
    }
  };

  const handleCopyWebhook = () => {
    if (!gateway) return;
    navigator.clipboard.writeText(getWebhookUrl(gateway.name));
    setCopied(true);
    toast.success('Webhook URL copied');
    setTimeout(() => setCopied(false), 2000);
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

  const readiness = getGatewayReadiness(gateway);
  const outstandingItems = readiness.items.filter(
    (item) => !item.done && item.id !== 'receiving-traffic',
  );

  return (
    <div className="space-y-6 rounded-lg border p-6">
      <Alert variant={readiness.ready ? 'success' : 'warning'}>
        {readiness.ready ? (
          <ShieldCheck className="h-4 w-4" />
        ) : (
          <AlertTriangle className="h-4 w-4" />
        )}
        <AlertTitle>
          {readiness.ready
            ? 'Ready to receive messages'
            : `${readiness.blockingCount} thing${readiness.blockingCount === 1 ? '' : 's'} left before this channel can receive messages`}
        </AlertTitle>
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

      <div className="space-y-2 rounded-lg border p-4">
        <p className="text-sm font-medium">Inbound webhook URL</p>
        <p className="text-xs text-muted-foreground">
          Paste this URL into the channel provider&apos;s configuration (e.g. Meta Developer
          Console).
        </p>
        <div className="flex items-center gap-2">
          <Input readOnly className="font-mono text-xs" value={getWebhookUrl(gateway.name)} />
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
      </div>

      <div className="flex justify-end">
        <Button type="button" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save channel settings'}
        </Button>
      </div>
    </div>
  );
}
