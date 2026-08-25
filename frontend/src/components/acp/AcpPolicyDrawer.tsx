import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Loader2, Shield } from 'lucide-react';
import type { AcpPolicy } from '@/services/acpApi';
import { createAcpPolicy, updateAcpPolicy } from '@/services/acpApi';
import { getAvailableAgents } from '@/services/gatewayApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

interface AcpPolicyDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  policy: AcpPolicy | null;
  onSaved: (policy: AcpPolicy) => void;
}

interface FormState {
  policy_name: string;
  enabled: 0 | 1;
  caller_type: AcpPolicy['caller_type'];
  caller_reference: string;
  scope_type: AcpPolicy['scope_type'];
  default_agent: string;
  allowed_agents: string;
  max_run_duration_seconds: number;
  allow_file_tools: 0 | 1;
  allow_shell_tools: 0 | 1;
  notes: string;
}

const emptyForm: FormState = {
  policy_name: '',
  enabled: 1,
  caller_type: 'remote_connection',
  caller_reference: '',
  scope_type: 'single_agent',
  default_agent: '',
  allowed_agents: '',
  max_run_duration_seconds: 300,
  allow_file_tools: 0,
  allow_shell_tools: 0,
  notes: '',
};

export function AcpPolicyDrawer({
  open,
  onOpenChange,
  policy,
  onSaved,
}: AcpPolicyDrawerProps) {
  const isEditing = Boolean(policy);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [agents, setAgents] = useState<{ name: string; agent_name: string }[]>([]);

  useEffect(() => {
    if (open) {
      getAvailableAgents().then(setAgents).catch(() => setAgents([]));
      if (policy) {
        setForm({
          policy_name: policy.policy_name || '',
          enabled: policy.enabled ?? 1,
          caller_type: policy.caller_type || 'remote_connection',
          caller_reference: policy.caller_reference || '',
          scope_type: policy.scope_type || 'single_agent',
          default_agent: policy.default_agent || '',
          allowed_agents:
            policy.allowed_agents?.map((row) => row.agent).join('\n') || '',
          max_run_duration_seconds: policy.max_run_duration_seconds ?? 300,
          allow_file_tools: policy.allow_file_tools ?? 0,
          allow_shell_tools: policy.allow_shell_tools ?? 0,
          notes: policy.notes || '',
        });
      } else {
        setForm(emptyForm);
      }
    }
  }, [open, policy]);

  const canSave = form.policy_name.trim();

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    try {
      const payload: Partial<AcpPolicy> = {
        policy_name: form.policy_name.trim(),
        enabled: form.enabled,
        caller_type: form.caller_type,
        caller_reference: form.caller_reference || undefined,
        scope_type: form.scope_type,
        max_run_duration_seconds: Number(form.max_run_duration_seconds) || 300,
        allow_file_tools: form.allow_file_tools,
        allow_shell_tools: form.allow_shell_tools,
        notes: form.notes,
      };

      if (form.scope_type === 'single_agent') {
        payload.default_agent = form.default_agent || undefined;
        payload.allowed_agents = [];
      } else {
        payload.default_agent = undefined;
        payload.allowed_agents = form.allowed_agents
          .split('\n')
          .map((a) => a.trim())
          .filter(Boolean)
          .map((agent) => ({ agent }));
      }

      const saved = policy
        ? await updateAcpPolicy(policy.name, payload)
        : await createAcpPolicy(payload as Omit<AcpPolicy, 'name'>);

      toast.success(policy ? 'Policy updated' : 'Policy created');
      onSaved(saved);
      onOpenChange(false);
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Could not save policy');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Shield className="h-4 w-4" />
            </div>
            {isEditing ? 'Configure policy' : 'Add policy'}
          </DialogTitle>
          <DialogDescription>
            Define which caller can reach which agents through ACP connections.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="flex items-center justify-between rounded-lg border border-line bg-paper p-3.5">
            <div>
              <p className="text-xs font-medium text-ink">Enabled</p>
              <p className="text-[11px] text-steel">
                Active policies are enforced during ACP session creation.
              </p>
            </div>
            <Switch
              checked={form.enabled === 1}
              onCheckedChange={(checked) =>
                setForm((f) => ({ ...f, enabled: checked ? 1 : 0 }))
              }
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="policy_name">
              Policy name <span className="text-destructive">*</span>
            </Label>
            <Input
              id="policy_name"
              value={form.policy_name}
              onChange={(e) =>
                setForm((f) => ({ ...f, policy_name: e.target.value }))
              }
              placeholder="e.g. Kimi Code local access"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="caller_type">Caller type</Label>
              <Select
                value={form.caller_type}
                onValueChange={(value) =>
                  setForm((f) => ({
                    ...f,
                    caller_type: value as AcpPolicy['caller_type'],
                  }))
                }
              >
                <SelectTrigger id="caller_type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="api_key">API key</SelectItem>
                  <SelectItem value="remote_connection">Remote connection</SelectItem>
                  <SelectItem value="user">User</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="caller_reference">Caller reference</Label>
              <Input
                id="caller_reference"
                value={form.caller_reference}
                onChange={(e) =>
                  setForm((f) => ({ ...f, caller_reference: e.target.value }))
                }
                placeholder="e.g. API key name or connection"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="scope_type">Scope type</Label>
            <Select
              value={form.scope_type}
              onValueChange={(value) =>
                setForm((f) => ({
                  ...f,
                  scope_type: value as AcpPolicy['scope_type'],
                }))
              }
            >
              <SelectTrigger id="scope_type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="single_agent">Single agent</SelectItem>
                <SelectItem value="agent_list">Allowed agent list</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {form.scope_type === 'single_agent' ? (
            <div className="space-y-2">
              <Label htmlFor="default_agent">Default agent</Label>
              <Select
                value={form.default_agent || '__none'}
                onValueChange={(value) =>
                  setForm((f) => ({
                    ...f,
                    default_agent: value === '__none' ? '' : value,
                  }))
                }
              >
                <SelectTrigger id="default_agent">
                  <SelectValue placeholder="Choose an agent…" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">None</SelectItem>
                  {agents.map((a) => (
                    <SelectItem key={a.name} value={a.name}>
                      {a.agent_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : (
            <div className="space-y-2">
              <Label htmlFor="allowed_agents">Allowed agents</Label>
              <Textarea
                id="allowed_agents"
                value={form.allowed_agents}
                onChange={(e) =>
                  setForm((f) => ({ ...f, allowed_agents: e.target.value }))
                }
                placeholder="One agent document name per line"
                rows={4}
              />
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="max_run_duration_seconds">Max run duration (seconds)</Label>
            <Input
              id="max_run_duration_seconds"
              type="number"
              min={1}
              value={form.max_run_duration_seconds}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  max_run_duration_seconds: Number(e.target.value),
                }))
              }
            />
          </div>

          <div className="flex items-center justify-between rounded-lg border border-line bg-paper p-3.5">
            <div>
              <p className="text-xs font-medium text-ink">Allow file tools</p>
            </div>
            <Switch
              checked={form.allow_file_tools === 1}
              onCheckedChange={(checked) =>
                setForm((f) => ({ ...f, allow_file_tools: checked ? 1 : 0 }))
              }
            />
          </div>

          <div className="flex items-center justify-between rounded-lg border border-line bg-paper p-3.5">
            <div>
              <p className="text-xs font-medium text-ink">Allow shell tools</p>
            </div>
            <Switch
              checked={form.allow_shell_tools === 1}
              onCheckedChange={(checked) =>
                setForm((f) => ({ ...f, allow_shell_tools: checked ? 1 : 0 }))
              }
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="notes">Notes</Label>
            <Textarea
              id="notes"
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              placeholder="Why this policy exists"
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!canSave || saving}>
            {saving ? (
              <>
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                Saving…
              </>
            ) : (
              'Save'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
