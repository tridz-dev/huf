import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { AlertTriangle, Check, Loader2, Plug, Plus, Send } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import type {
  ConnectableAgent,
  ConnectionTestResult,
  ExternalConnection,
  ExternalHubTier,
} from '@/types/external/agents.types';
import {
  createExternalConnection,
  listConnectableAgents,
  listExternalConnections,
  setAgentExecutionMode,
  testExternalConnection,
  updateExternalConnection,
} from '@/services/external/agentsApi';
import { AssignTaskDialog } from './AssignTaskDialog';
import { ConnectionSetupDialog } from './ConnectionSetupDialog';

type Connection = ExternalConnection;
type RuntimeKind = Connection['runtime_kind'];
type Policy = Connection['read_policy'];
type PolicyField = 'read_policy' | 'write_policy' | 'communicate_policy';
type ConnectionPatch = Partial<Pick<Connection, 'enabled' | 'hub_tier' | PolicyField>>;

const RUNTIME_LABELS: Record<RuntimeKind, string> = {
  claude_code: 'Claude Code',
  codex: 'Codex',
  other: 'Other',
};

const RUNTIME_OPTIONS: { value: RuntimeKind; label: string }[] = [
  { value: 'claude_code', label: RUNTIME_LABELS.claude_code },
  { value: 'codex', label: RUNTIME_LABELS.codex },
  { value: 'other', label: RUNTIME_LABELS.other },
];

const POLICY_OPTIONS: { value: Policy; label: string }[] = [
  { value: 'Allow', label: 'Allow' },
  { value: 'Requires Approval', label: 'Needs approval' },
  { value: 'Deny', label: 'Block' },
];

const POLICY_FIELDS: { field: PolicyField; label: string }[] = [
  { field: 'read_policy', label: 'Read records' },
  { field: 'write_policy', label: 'Change records' },
  { field: 'communicate_policy', label: 'Send messages' },
];

const HUB_TIER_OPTIONS: { value: ExternalHubTier; label: string }[] = [
  { value: 'Off', label: 'Off' },
  { value: 'Build', label: 'Can build with my approval' },
  { value: 'Admin', label: 'Admin builder' },
];

const isHubTier = (value: string): value is ExternalHubTier =>
  HUB_TIER_OPTIONS.some((option) => option.value === value);

const isPolicy = (value: string): value is Policy =>
  POLICY_OPTIONS.some((option) => option.value === value);

const isRuntimeKind = (value: string): value is RuntimeKind =>
  RUNTIME_OPTIONS.some((option) => option.value === value);

const formatLastSeen = (value: Connection['last_seen']): string => {
  if (!value) return 'Not seen yet';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not seen yet' : date.toLocaleString();
};

export function ConnectionsSection() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [testingName, setTestingName] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, ConnectionTestResult>>({});
  const [setupConnection, setSetupConnection] = useState<Connection | null>(null);
  const [taskConnection, setTaskConnection] = useState<Connection | null>(null);

  const loadConnections = useCallback(async () => {
    try {
      const rows = await listExternalConnections();
      setConnections(rows);
    } catch {
      toast.error("Couldn't load connected agents. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConnections();
  }, [loadConnections]);

  const saveChange = async (connection: Connection, patch: ConnectionPatch) => {
    setConnections((prev) =>
      prev.map((row) => (row.name === connection.name ? { ...row, ...patch } : row)),
    );
    try {
      await updateExternalConnection(connection.name, patch);
      toast.success('Connection updated');
    } catch {
      setConnections((prev) =>
        prev.map((row) => (row.name === connection.name ? connection : row)),
      );
      toast.error("Couldn't save that change. Please try again.");
    }
  };

  const runTest = async (connection: Connection) => {
    setTestingName(connection.name);
    try {
      const result = await testExternalConnection(connection.name);
      setTestResults((prev) => ({ ...prev, [connection.name]: result }));
    } catch {
      toast.error("Couldn't check this connection. Please try again.");
    } finally {
      setTestingName(null);
    }
  };

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">Connected agents</h2>
        <ConnectAgentDialog onConnected={loadConnections} />
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading connected agents...</p>
      ) : connections.length === 0 ? (
        <p className="text-sm text-muted-foreground">No agents connected yet.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {connections.map((connection) => (
            <Card key={connection.name}>
              <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
                <div className="min-w-0">
                  <CardTitle className="truncate text-base">{connection.agent}</CardTitle>
                  <p className="text-sm text-muted-foreground">
                    {RUNTIME_LABELS[connection.runtime_kind]}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Label htmlFor={`enabled-${connection.name}`} className="text-sm">
                    Enabled
                  </Label>
                  <Switch
                    id={`enabled-${connection.name}`}
                    checked={connection.enabled === 1}
                    onCheckedChange={(checked) =>
                      void saveChange(connection, { enabled: checked ? 1 : 0 })
                    }
                  />
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor={`hub_tier-${connection.name}`} className="text-xs text-muted-foreground">
                    Builder access
                  </Label>
                  <Select
                    value={connection.hub_tier}
                    onValueChange={(value) => {
                      if (isHubTier(value)) {
                        void saveChange(connection, { hub_tier: value });
                      }
                    }}
                  >
                    <SelectTrigger id={`hub_tier-${connection.name}`} className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {HUB_TIER_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    Lets the connected app find and, with your approval, create agents, tools, tables
                    and apps.
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  {POLICY_FIELDS.map(({ field, label }) => {
                    const selectId = `${field}-${connection.name}`;
                    return (
                      <div key={field} className="space-y-1.5">
                        <Label htmlFor={selectId} className="text-xs text-muted-foreground">
                          {label}
                        </Label>
                        <Select
                          value={connection[field]}
                          onValueChange={(value) => {
                            if (isPolicy(value)) {
                              void saveChange(connection, { [field]: value });
                            }
                          }}
                        >
                          <SelectTrigger id={selectId} className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {POLICY_OPTIONS.map((option) => (
                              <SelectItem key={option.value} value={option.value}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    );
                  })}
                </div>
                <ConnectionTestPanel result={testResults[connection.name]} />

                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs text-muted-foreground">
                    Last seen: {formatLastSeen(connection.last_seen)}
                  </p>
                  <div className="flex items-center gap-2">
                    {connection.enabled === 1 && (
                      <Button variant="outline" size="sm" onClick={() => setTaskConnection(connection)}>
                        <Send className="mr-2 h-3.5 w-3.5" />
                        Send a task
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void runTest(connection)}
                      disabled={testingName !== null}
                    >
                      {testingName === connection.name ? (
                        <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Plug className="mr-2 h-3.5 w-3.5" />
                      )}
                      Test
                    </Button>
                    <Button size="sm" onClick={() => setSetupConnection(connection)}>
                      Set up
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {taskConnection && (
        <AssignTaskDialog
          open
          onOpenChange={(next) => {
            if (!next) setTaskConnection(null);
          }}
          connection={taskConnection.name}
          agentName={taskConnection.agent}
        />
      )}

      {setupConnection && (
        <ConnectionSetupDialog
          open
          onOpenChange={(next) => {
            if (!next) setSetupConnection(null);
          }}
          connection={setupConnection.name}
          agentName={setupConnection.agent}
          hasSiblings={connections.length > 1}
        />
      )}
    </section>
  );
}

interface ConnectionTestPanelProps {
  result?: ConnectionTestResult;
}

function ConnectionTestPanel({ result }: ConnectionTestPanelProps) {
  if (!result) return null;

  if (result.ok) {
    return (
      <p className="flex items-center gap-2 text-sm text-green-600">
        <Check className="h-4 w-4" />
        Ready. {result.tools} {result.tools === 1 ? 'tool is' : 'tools are'} available.
      </p>
    );
  }

  return (
    <div className="space-y-1.5 rounded-md border border-destructive/40 p-3">
      <p className="flex items-center gap-2 text-sm font-medium text-destructive">
        <AlertTriangle className="h-4 w-4" />
        This connection needs attention
      </p>
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        {result.problems.map((problem) => (
          <li key={problem}>{problem}</li>
        ))}
      </ul>
    </div>
  );
}

interface ConnectAgentDialogProps {
  onConnected: () => Promise<void> | void;
}

function ConnectAgentDialog({ onConnected }: ConnectAgentDialogProps) {
  const [open, setOpen] = useState(false);
  const [agents, setAgents] = useState<ConnectableAgent[]>([]);
  const [isLoadingAgents, setIsLoadingAgents] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string>('');
  const [runtimeKind, setRuntimeKind] = useState<RuntimeKind>('claude_code');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleOpenChange = async (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) {
      setSelectedAgent('');
      setRuntimeKind('claude_code');
      return;
    }
    setIsLoadingAgents(true);
    try {
      setAgents(await listConnectableAgents());
    } catch {
      toast.error("Couldn't load your agents. Please try again.");
    } finally {
      setIsLoadingAgents(false);
    }
  };

  const handleConnect = async () => {
    const agent = agents.find((row) => row.name === selectedAgent);
    if (!agent) return;

    setIsSubmitting(true);
    try {
      if (agent.execution_mode === 'Native') {
        await setAgentExecutionMode(agent.name, 'Connected External');
      }
      await createExternalConnection({ agent: agent.name, runtime_kind: runtimeKind });
      await onConnected();
      toast.success(`${agent.agent_name} connected`);
      void handleOpenChange(false);
    } catch {
      toast.error("Couldn't connect this agent. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => void handleOpenChange(next)}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="mr-2 h-4 w-4" />
          Connect an agent
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Connect an agent</DialogTitle>
          <DialogDescription>
            Your own AI app uses Huf's tools with your permissions. Changes and messages can
            require your approval.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="connect-agent">Agent</Label>
            <Select
              value={selectedAgent}
              onValueChange={setSelectedAgent}
              disabled={isLoadingAgents}
            >
              <SelectTrigger id="connect-agent" className="w-full">
                <SelectValue placeholder={isLoadingAgents ? 'Loading agents...' : 'Choose an agent'} />
              </SelectTrigger>
              <SelectContent>
                {agents.map((agent) => (
                  <SelectItem key={agent.name} value={agent.name}>
                    {agent.agent_name}
                    {agent.execution_mode === 'Native' ? ' (will switch to external mode)' : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="connect-runtime">Runtime</Label>
            <Select
              value={runtimeKind}
              onValueChange={(value) => {
                if (isRuntimeKind(value)) setRuntimeKind(value);
              }}
            >
              <SelectTrigger id="connect-runtime" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RUNTIME_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => void handleOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void handleConnect()} disabled={!selectedAgent || isSubmitting}>
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Connect
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
