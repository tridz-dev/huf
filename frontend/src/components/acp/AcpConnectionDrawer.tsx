import { useEffect, useMemo, useState } from 'react';
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
import { Loader2, Plug, TestTube } from 'lucide-react';
import type { AcpConnection, AcpRegistryEntry, AcpConnectionTestResult } from '@/services/acpApi';
import {
  createAcpConnection,
  updateAcpConnection,
  testAcpConnection,
} from '@/services/acpApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

interface AcpConnectionDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  connection: AcpConnection | null;
  registryEntries: AcpRegistryEntry[];
  onSaved: (connection: AcpConnection) => void;
}

const emptyForm = {
  connection_name: '',
  enabled: 1 as 0 | 1,
  acp_registry_entry: '',
  auth_secret: '',
  max_concurrent_sessions: 3,
  session_ttl_seconds: 300,
};

export function AcpConnectionDrawer({
  open,
  onOpenChange,
  connection,
  registryEntries,
  onSaved,
}: AcpConnectionDrawerProps) {
  const isEditing = Boolean(connection);
  const [form, setForm] = useState<typeof emptyForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<AcpConnectionTestResult | null>(null);

  useEffect(() => {
    if (open) {
      if (connection) {
        setForm({
          connection_name: connection.connection_name || '',
          enabled: connection.enabled ?? 1,
          acp_registry_entry: connection.acp_registry_entry || '',
          auth_secret: '', // Password field is never round-tripped.
          max_concurrent_sessions: connection.max_concurrent_sessions ?? 3,
          session_ttl_seconds: connection.session_ttl_seconds ?? 300,
        });
      } else {
        setForm(emptyForm);
      }
      setTestResult(null);
    }
  }, [open, connection]);

  const selectedRegistry = useMemo(
    () => registryEntries.find((r) => r.name === form.acp_registry_entry),
    [registryEntries, form.acp_registry_entry]
  );

  const canSave =
    form.connection_name.trim() && form.acp_registry_entry;

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    try {
      const payload = {
        connection_name: form.connection_name.trim(),
        enabled: form.enabled,
        protocol_type: 'acp_stdio' as const,
        acp_registry_entry: form.acp_registry_entry,
        max_concurrent_sessions: Number(form.max_concurrent_sessions) || 3,
        session_ttl_seconds: Number(form.session_ttl_seconds) || 300,
        ...(form.auth_secret ? { auth_secret: form.auth_secret } : {}),
      };

      const saved = connection
        ? await updateAcpConnection(connection.name, payload)
        : await createAcpConnection(payload);

      toast.success(
        connection ? 'Connection updated' : 'Connection created'
      );
      onSaved(saved);
      onOpenChange(false);
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Could not save connection');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!connection) {
      toast.info('Save the connection before testing it.');
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testAcpConnection(connection.name);
      setTestResult(result);
      if (result.ok) {
        toast.success('ACP handshake succeeded', {
          description: result.agent_name
            ? `Connected to ${result.agent_name}`
            : 'Initialize handshake completed.',
        });
      } else {
        toast.error('ACP handshake failed', {
          description: result.error || 'Unknown error',
        });
      }
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Connection test failed');
    } finally {
      setTesting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Plug className="h-4 w-4" />
            </div>
            {isEditing ? 'Configure ACP connection' : 'Add ACP connection'}
          </DialogTitle>
          <DialogDescription>
            Connect an external ACP agent that this Huf instance can call as a tool.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="flex items-center justify-between rounded-lg border border-line bg-paper p-3.5">
            <div>
              <p className="text-xs font-medium text-ink">Enabled</p>
              <p className="text-[11px] text-steel">
                Allow agents to invoke this connection as a tool.
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
            <Label htmlFor="connection_name">
              Connection name <span className="text-destructive">*</span>
            </Label>
            <Input
              id="connection_name"
              value={form.connection_name}
              onChange={(e) =>
                setForm((f) => ({ ...f, connection_name: e.target.value }))
              }
              placeholder="e.g. Kimi Code — local"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="acp_registry_entry">
              ACP command registry <span className="text-destructive">*</span>
            </Label>
            <Select
              value={form.acp_registry_entry}
              onValueChange={(value) =>
                setForm((f) => ({ ...f, acp_registry_entry: value }))
              }
            >
              <SelectTrigger id="acp_registry_entry">
                <SelectValue placeholder="Choose an allowed command shape…" />
              </SelectTrigger>
              <SelectContent>
                {registryEntries.map((entry) => (
                  <SelectItem key={entry.name} value={entry.name}>
                    {entry.registry_name} — {entry.binary_path}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-steel-soft">
              Registry entries are admin-curated: they fix the binary path, argument shape,
              working directory, and allowed environment variables.
            </p>
          </div>

          {selectedRegistry && (
            <div className="rounded-md border border-line bg-paper p-3 text-xs space-y-1">
              <p>
                <span className="text-steel-soft">Binary:</span>{' '}
                <span className="font-mono">{selectedRegistry.binary_path}</span>
              </p>
              <p>
                <span className="text-steel-soft">Args:</span>{' '}
                <span className="font-mono">
                  {Array.isArray(selectedRegistry.argv_shape)
                    ? JSON.stringify(selectedRegistry.argv_shape)
                    : selectedRegistry.argv_shape}
                </span>
              </p>
              <p>
                <span className="text-steel-soft">Working directory:</span>{' '}
                <span className="font-mono">{selectedRegistry.working_directory}</span>
              </p>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="auth_secret">Auth secret</Label>
            <Input
              id="auth_secret"
              type="password"
              value={form.auth_secret}
              onChange={(e) =>
                setForm((f) => ({ ...f, auth_secret: e.target.value }))
              }
              placeholder={
                isEditing ? 'Leave blank to keep the saved secret' : 'Optional token or API key'
              }
            />
            <p className="text-xs text-steel-soft">
              Injected into the subprocess under the registry entry’s configured env key.
              Never shown back after saving.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="max_concurrent_sessions">Max concurrent sessions</Label>
              <Input
                id="max_concurrent_sessions"
                type="number"
                min={1}
                value={form.max_concurrent_sessions}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    max_concurrent_sessions: Number(e.target.value),
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="session_ttl_seconds">Session TTL (seconds)</Label>
              <Input
                id="session_ttl_seconds"
                type="number"
                min={1}
                value={form.session_ttl_seconds}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    session_ttl_seconds: Number(e.target.value),
                  }))
                }
              />
            </div>
          </div>

          {isEditing && (
            <div className="rounded-md border border-line p-3 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <Label className="text-xs">Connection health</Label>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleTest}
                  disabled={testing}
                >
                  {testing ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <TestTube className="mr-1.5 h-3.5 w-3.5" />
                  )}
                  {testing ? 'Testing…' : 'Test Connection'}
                </Button>
              </div>
              {testResult && (
                <div className="text-sm">
                  {testResult.ok ? (
                    <div className="space-y-1 text-good">
                      <p>Handshake successful.</p>
                      {testResult.protocol_version !== undefined && (
                        <p className="text-xs text-steel-soft">
                          Protocol version: {testResult.protocol_version}
                        </p>
                      )}
                      {testResult.agent_name && (
                        <p className="text-xs text-steel-soft">
                          Agent: {testResult.agent_name}
                        </p>
                      )}
                    </div>
                  ) : (
                    <div className="space-y-1 text-destructive">
                      <p>Handshake failed.</p>
                      {testResult.error && (
                        <p className="text-xs break-words">{testResult.error}</p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
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
