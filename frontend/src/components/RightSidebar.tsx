import { toast } from 'sonner';
import { useState, useEffect } from 'react';
import { X, Settings, Edit, Trash2, Clock } from 'lucide-react';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Button } from './ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Label } from './ui/label';
import { Combobox } from './ui/combobox';
import { Checkbox } from './ui/checkbox';
import { linkRoutes } from '@/lib/link-routes';
import { cn } from '@/lib/utils';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from './ui/alert-dialog';
import { useFlowContext } from '../contexts/FlowContext';
import { NodeSelectionModal } from './modals/NodeSelectionModal';
import { ScheduleIntervalType, DocEventType, ScheduleTriggerConfig } from '../types/flow.types';
import { getAgents, getDocTypes, getRoles } from '../services/agentApi';
import { getToolFunctions, getToolFunction, getFlowTools, type FlowTool } from '../services/toolApi';
import { VariablePicker } from './ui/VariablePicker';
import { JsonSchemaForm } from './JsonSchemaForm';

/**
 * Computes a human-readable summary of a schedule trigger's cadence, e.g.
 * "Runs every 5 minutes". Only handles the simple interval case (every N
 * minutes/hours/days) since that can be described with plain arithmetic; the
 * custom-cron case is intentionally left unhandled (returns null) because
 * there's no cron-parsing library in this project to describe it reliably —
 * showing a wrong or placeholder value would be worse than showing nothing.
 *
 * This deliberately does NOT claim to be an exact "next run" time: the
 * backend does not expose a real next-execution timestamp to the frontend
 * (no such field exists on ScheduleTriggerConfig or node data), so there is
 * no honest way to compute when the schedule actually last fired or its real
 * anchor point. Presenting "now + interval" as the next run time would be
 * misleading, not just approximate — it would always read "in N minutes"
 * regardless of the schedule's true state.
 */
function computeScheduleNextRun(config: ScheduleTriggerConfig): string | null {
  if (config.intervalType === 'custom') {
    return null;
  }

  const unitLabels: Record<'minutes' | 'hours' | 'days', string> = {
    minutes: 'minute',
    hours: 'hour',
    days: 'day',
  };
  const unitLabel = unitLabels[config.intervalType as 'minutes' | 'hours' | 'days'];
  if (!unitLabel) {
    return null;
  }

  const interval = config.interval && config.interval > 0 ? config.interval : 1;
  const pluralizedUnit = interval === 1 ? unitLabel : `${unitLabel}s`;

  return `Runs every ${interval} ${pluralizedUnit}`;
}

interface ToolParameter {
  fieldname: string;
  label?: string;
  type: string;
  required?: boolean;
  description?: string;
}

interface ToolDetails {
  parameters?: ToolParameter[];
  /** Present only when the tool came from list_flow_tools() (built-in or MCP). */
  params_json_schema?: Record<string, unknown>;
}

interface RightSidebarProps {
  onToggle: () => void;
  variant?: 'panel' | 'sheet';
}

export function RightSidebar({ onToggle, variant = 'panel' }: RightSidebarProps) {
  const { activeFlow, selectedNodeId, selectedEdgeId, updateNode, deleteNode, updateEdges } = useFlowContext();
  const selectedNode = activeFlow?.nodes.find((n) => n.id === selectedNodeId);
  const selectedEdge = activeFlow?.edges.find((e) => e.id === selectedEdgeId);
  const [isChangingTrigger, setIsChangingTrigger] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [agents, setAgents] = useState<Array<{ value: string; label: string }>>([]);
  const [tools, setTools] = useState<Array<{ value: string; label: string; subtitle?: string }>>([]);
  const [flowToolsByName, setFlowToolsByName] = useState<Record<string, FlowTool>>({});
  const [flowToolsDegraded, setFlowToolsDegraded] = useState(false);
  const [docTypes, setDocTypes] = useState<Array<{ value: string; label: string }>>([]);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [loadingTools, setLoadingTools] = useState(false);
  const [loadingDocTypes, setLoadingDocTypes] = useState(false);
  const [selectedToolDetails, setSelectedToolDetails] = useState<ToolDetails | null>(null);
  const [loadingToolDetails, setLoadingToolDetails] = useState(false);
  const [roles, setRoles] = useState<Array<{ value: string; label: string }>>([]);
  const [loadingRoles, setLoadingRoles] = useState(false);

  // Load agents when agent-run or router node selected
  useEffect(() => {
    const actionType = selectedNode?.data.actionConfig?.type;
    if (!selectedNode?.data.actionConfig || !actionType || !['agent-run', 'router', 'tool-call'].includes(actionType)) return;
    setLoadingAgents(true);
    getAgents()
      .then((result) => {
        const items = Array.isArray(result) ? result : result.items;
        setAgents(
          (items || []).map((a: { name: string; agent_name?: string; model?: string }) => ({
            value: a.name,
            label: a.model
              ? `${a.agent_name || a.name} · ${a.model}`
              : a.agent_name || a.name,
          }))
        );
      })
      .catch(() => setAgents([]))
      .finally(() => setLoadingAgents(false));
  }, [selectedNode?.id, selectedNode?.data.actionConfig]);

  // Load tools when tool-call node selected. Prefer the unified list_flow_tools()
  // (built-in + MCP), grouped by source; fall back to the legacy Agent Tool Function
  // list if that endpoint isn't available yet (contract not deployed, older backend, etc).
  useEffect(() => {
    if (!selectedNode?.data.actionConfig || selectedNode.data.actionConfig.type !== 'tool-call') return;
    setLoadingTools(true);
    setFlowToolsDegraded(false);

    getFlowTools()
      .then((list) => {
        const byName: Record<string, FlowTool> = {};
        (list || []).forEach((t) => { byName[t.name] = t; });
        setFlowToolsByName(byName);

        // Group by source so built-in and each MCP server cluster together; the group
        // is surfaced as a subtitle since Combobox renders a single flat list.
        const sorted = [...(list || [])].sort((a, b) => {
          const groupA = a.source === 'mcp' ? `mcp:${a.mcp_server || ''}` : 'builtin';
          const groupB = b.source === 'mcp' ? `mcp:${b.mcp_server || ''}` : 'builtin';
          if (groupA !== groupB) return groupA.localeCompare(groupB);
          return (a.label || a.name).localeCompare(b.label || b.name);
        });
        setTools(
          sorted.map((t) => ({
            value: t.name,
            label: t.label || t.name,
            subtitle: t.source === 'mcp' ? `MCP: ${t.mcp_server || 'unknown server'}` : 'Built-in',
          }))
        );
      })
      .catch(() => {
        // Graceful degradation: list_flow_tools() may not exist yet on this backend.
        setFlowToolsDegraded(true);
        setFlowToolsByName({});
        return getToolFunctions()
          .then((list) => {
            setTools(
              (list || []).map((t: { name: string; tool_name?: string }) => ({
                value: t.tool_name || t.name,
                label: t.tool_name || t.name,
              }))
            );
          })
          .catch(() => setTools([]));
      })
      .finally(() => setLoadingTools(false));
  }, [selectedNode?.id, selectedNode?.data.actionConfig]);

  // Load specific tool details when a tool is selected
  useEffect(() => {
    if (!selectedNode?.data.actionConfig || selectedNode.data.actionConfig.type !== 'tool-call') {
      setSelectedToolDetails(null);
      return;
    }

    const toolName = selectedNode.data.actionConfig.tool_name;
    if (!toolName) {
      setSelectedToolDetails(null);
      return;
    }

    // If list_flow_tools() succeeded, we already have this tool's JSON Schema in memory —
    // no need for a second round-trip, and this also covers MCP tools which have no
    // Agent Tool Function doc for getToolFunction() to fetch.
    if (!flowToolsDegraded && flowToolsByName[toolName]) {
      const flowTool = flowToolsByName[toolName];
      setSelectedToolDetails({ params_json_schema: flowTool.params_json_schema || {} });
      setLoadingToolDetails(false);
      return;
    }

    setLoadingToolDetails(true);
    getToolFunction(toolName)
      .then((details) => {
        setSelectedToolDetails(details);
      })
      .catch(() => setSelectedToolDetails(null))
      .finally(() => setLoadingToolDetails(false));
  }, [selectedNode?.id, selectedNode?.data.actionConfig?.type === 'tool-call' ? selectedNode.data.actionConfig.tool_name : undefined, flowToolsDegraded, flowToolsByName]);

  // Load DocTypes when doc-event trigger or human-in-loop node selected
  useEffect(() => {
    const isDocEvent = selectedNode?.data.triggerConfig && selectedNode.data.triggerConfig.type === 'doc-event';
    const isHumanInLoop = selectedNode?.data.actionConfig && selectedNode.data.actionConfig.type === 'human.approval';
    if (!isDocEvent && !isHumanInLoop) return;
    if (docTypes.length > 0) return; // already loaded
    setLoadingDocTypes(true);
    getDocTypes()
      .then((list) => {
        setDocTypes(
          (list || []).map((dt: { name: string }) => ({ value: dt.name, label: dt.name }))
        );
      })
      .catch(() => setDocTypes([]))
      .finally(() => setLoadingDocTypes(false));
  }, [selectedNode?.id, selectedNode?.data.triggerConfig, selectedNode?.data.actionConfig]);

  // Load roles when human-in-loop node selected
  useEffect(() => {
    if (!selectedNode?.data.actionConfig || selectedNode.data.actionConfig.type !== 'human.approval') return;
    if (roles.length > 0) return; // already loaded
    setLoadingRoles(true);
    getRoles()
      .then((list) => {
        setRoles(
          (list || []).map((r: { name: string }) => ({ value: r.name, label: r.name }))
        );
      })
      .catch(() => setRoles([]))
      .finally(() => setLoadingRoles(false));
  }, [selectedNode?.id, selectedNode?.data.actionConfig]);

  const handleUpdateLabel = (label: string) => {
    if (selectedNodeId) {
      updateNode(selectedNodeId, {
        data: {
          ...selectedNode!.data,
          label
        }
      });
    }
  };

  const handleUpdateTriggerConfig = (field: string, value: unknown) => {
    if (selectedNodeId && selectedNode?.data.triggerConfig) {
      updateNode(selectedNodeId, {
        data: {
          ...selectedNode.data,
          triggerConfig: {
            ...selectedNode.data.triggerConfig,
            [field]: value
          }
        }
      });
    }
  };

  const renderTriggerForm = () => {
    if (!selectedNode?.data.triggerConfig) return null;
    const config = selectedNode.data.triggerConfig;

    if (config.type === 'webhook') {
      const webhookUrl = `${window.location.origin}/api/method/huf.ai.flow_api.flow_webhook?flow_id=${activeFlow?.id || '{flow_id}'}&webhook_key=${config.auth || '{key}'}`;

      return (
        <div className="space-y-3">
          <div>
            <Label size="sm">Webhook URL (Auto-generated)</Label>
            <div className="flex gap-2 mt-1">
              <Input
                readOnly
                value={webhookUrl}
                className="bg-muted/50 font-mono text-xs text-muted-foreground"
              />
              <Button
                variant="outline"
                size="icon"
                onClick={() => {
                  navigator.clipboard.writeText(webhookUrl);
                  toast.success('Webhook URL copied to clipboard');
                }}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2" /><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" /></svg>
              </Button>
            </div>
          </div>
          <div>
            <Label htmlFor="webhook-auth" size="sm">Authentication key (optional)</Label>
            <Input
              id="webhook-auth"
              value={config.auth || ''}
              onChange={(e) => handleUpdateTriggerConfig('auth', e.target.value)}
              placeholder="e.g. my-secret-key-123"
            />
          </div>
          <div>
            <Label htmlFor="method" size="sm">HTTP method (expected)</Label>
            <Select
              value={config.method || 'POST'}
              onValueChange={(value) => handleUpdateTriggerConfig('method', value)}
            >
              <SelectTrigger id="method">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="GET">GET</SelectItem>
                <SelectItem value="POST">POST</SelectItem>
                <SelectItem value="PUT">PUT</SelectItem>
                <SelectItem value="DELETE">DELETE</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      );
    }

    if (config.type === 'schedule') {
      const scheduleTypeSelect = (
        <Select
          value={config.intervalType}
          onValueChange={(value) => handleUpdateTriggerConfig('intervalType', value as ScheduleIntervalType)}
        >
          <SelectTrigger id="interval-type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="minutes">Minutes</SelectItem>
            <SelectItem value="hours">Hours</SelectItem>
            <SelectItem value="days">Days</SelectItem>
            <SelectItem value="custom">Custom (cron)</SelectItem>
          </SelectContent>
        </Select>
      );

      return (
        <>
          {config.intervalType !== 'custom' ? (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label htmlFor="interval">Every</Label>
                <Input
                  id="interval"
                  type="number"
                  min="1"
                  value={config.interval || 1}
                  onChange={(e) => handleUpdateTriggerConfig('interval', parseInt(e.target.value))}
                />
              </div>
              <div>
                <Label htmlFor="interval-type">Unit</Label>
                {scheduleTypeSelect}
              </div>
            </div>
          ) : (
            <div>
              <Label htmlFor="interval-type">Schedule type</Label>
              {scheduleTypeSelect}
            </div>
          )}
          {config.intervalType === 'custom' && (
            <div>
              <Label htmlFor="cron">Cron expression</Label>
              <Input
                id="cron"
                value={config.cronExpression || ''}
                onChange={(e) => handleUpdateTriggerConfig('cronExpression', e.target.value)}
                placeholder="0 */6 * * *"
              />
            </div>
          )}
        </>
      );
    }

    if (config.type === 'doc-event') {
      return (
        <>
          <div>
            <Label htmlFor="doctype">Document type</Label>
            <Combobox
              options={docTypes}
              value={config.doctype || ''}
              onValueChange={(v) => handleUpdateTriggerConfig('doctype', v)}
              placeholder={loadingDocTypes ? 'Loading...' : 'Select DocType...'}
              disabled={loadingDocTypes}
              searchPlaceholder="Search DocType..."
              emptyText="No DocType found."
            />
          </div>
          <div>
            <Label htmlFor="event">Event type</Label>
            <Select
              value={config.event}
              onValueChange={(value) => handleUpdateTriggerConfig('event', value as DocEventType)}
            >
              <SelectTrigger id="event">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="save">Save</SelectItem>
                <SelectItem value="update">Update</SelectItem>
                <SelectItem value="delete">Delete</SelectItem>
                <SelectItem value="before-save">Before save</SelectItem>
                <SelectItem value="before-update">Before update</SelectItem>
                <SelectItem value="before-delete">Before delete</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </>
      );
    }

    if (config.type === 'app-trigger') {
      return (
        <>
          <div>
            <Label htmlFor="integration">Integration</Label>
            <Input
              id="integration"
              value={config.integration || ''}
              readOnly
              className="bg-muted"
            />
          </div>
          <div>
            <Label htmlFor="event">Event</Label>
            <Input
              id="event"
              value={config.event || ''}
              onChange={(e) => handleUpdateTriggerConfig('event', e.target.value)}
              placeholder="e.g., new_message, new_email"
            />
          </div>
        </>
      );
    }

    return null;
  };

  const isSheet = variant === 'sheet';

  const scheduleNextRun =
    selectedNode?.data.nodeType === 'trigger' && selectedNode.data.triggerConfig?.type === 'schedule'
      ? computeScheduleNextRun(selectedNode.data.triggerConfig as ScheduleTriggerConfig)
      : null;

  return (
    <div
      className={cn(
        'relative bg-card flex flex-col w-[300px]',
        isSheet ? 'h-full' : 'h-screen border-l border-border',
      )}
    >
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
        {!selectedNode && !selectedEdge ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Settings className="w-12 h-12 text-muted-foreground mb-4" />
            <div className="text-sm text-muted-foreground">
              Select a node or edge to view configuration
            </div>
          </div>
        ) : selectedEdge ? (
          <>
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="text-sm font-semibold">Edge Configuration</div>
              </div>
            </div>

            <div>
              <Label htmlFor="edge-label">Edge label</Label>
              <Input
                id="edge-label"
                value={(selectedEdge.label as string) || ''}
                onChange={(e) => {
                  if (!activeFlow) return;
                  updateEdges(
                    activeFlow.edges.map((edge) =>
                      edge.id === selectedEdge.id ? { ...edge, label: e.target.value } : edge
                    )
                  );
                }}
                className="font-medium"
                placeholder="Optional label..."
              />
            </div>

            <div className="border-t border-border" />

            <div className="space-y-4">
              <div>
                <Label htmlFor="edge-type" size="sm">Edge type</Label>
                <Select
                  value={selectedEdge.data?.edgeType || 'always'}
                  onValueChange={(value) => {
                    if (!activeFlow) return;
                    updateEdges(
                      activeFlow.edges.map((edge) =>
                        edge.id === selectedEdge.id ? { ...edge, data: { ...edge.data, edgeType: value } } : edge
                      )
                    );
                  }}
                >
                  <SelectTrigger id="edge-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="always">Always (default)</SelectItem>
                    <SelectItem value="on_success">On success</SelectItem>
                    <SelectItem value="on_failure">On failure</SelectItem>
                    <SelectItem value="expression">Expression</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {selectedEdge.data?.edgeType === 'expression' && (
                <div>
                  <Label htmlFor="edge-expr" size="sm">Condition expression</Label>
                  <Input
                    id="edge-expr"
                    value={selectedEdge.data?.condition || ''}
                    onChange={(e) => {
                      if (!activeFlow) return;
                      updateEdges(
                        activeFlow.edges.map((edge) =>
                          edge.id === selectedEdge.id ? { ...edge, data: { ...edge.data, condition: e.target.value } } : edge
                        )
                      );
                    }}
                    placeholder='e.g., context["status"] == "approved"'
                  />
                </div>
              )}

              <div>
                <Label htmlFor="edge-priority" size="sm">Priority</Label>
                <Input
                  id="edge-priority"
                  type="number"
                  value={selectedEdge.data?.priority ?? 0}
                  onChange={(e) => {
                    if (!activeFlow) return;
                    const priority = e.target.value === '' ? 0 : Number(e.target.value);
                    updateEdges(
                      activeFlow.edges.map((edge) =>
                        edge.id === selectedEdge.id ? { ...edge, data: { ...edge.data, priority } } : edge
                      )
                    );
                  }}
                />
                <p className="text-[10px] text-muted-foreground mt-1">Higher priority edges are evaluated first</p>
              </div>

              <div>
                <Label htmlFor="edge-outcome" size="sm">Approval outcome</Label>
                <Select
                  value={selectedEdge.data?.meta?.outcome || 'none'}
                  onValueChange={(value) => {
                    if (!activeFlow) return;
                    updateEdges(
                      activeFlow.edges.map((edge) => {
                        if (edge.id !== selectedEdge.id) return edge;
                        const meta = { ...(edge.data?.meta || {}) };
                        if (value === 'none') {
                          delete meta.outcome;
                        } else {
                          meta.outcome = value;
                        }
                        return { ...edge, data: { ...edge.data, meta } };
                      })
                    );
                  }}
                >
                  <SelectTrigger id="edge-outcome">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    <SelectItem value="approved">approved</SelectItem>
                    <SelectItem value="rejected">rejected</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-muted-foreground mt-1">For edges leaving a Human Approval node: route this edge when the decision matches.</p>
              </div>
            </div>
          </>
        ) : selectedNode ? (
          <>
            <div className="-mx-3.5 -mt-3.5 mb-0 h-10 px-3.5 flex items-center gap-2 border-b border-border shrink-0">
              <span className="text-[13px] leading-none truncate" style={{ fontWeight: 590 }}>
                {selectedNode.data.label}
              </span>
              <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground bg-muted px-1.5 py-0.5 rounded shrink-0">
                {selectedNode.data.nodeType}
              </span>
              <div className="flex-1" />
              <Button
                variant="ghost"
                size="icon-sm"
                className="text-muted-foreground hover:text-destructive"
                onClick={() => setShowDeleteConfirm(true)}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                className="hover:bg-accent"
                onClick={onToggle}
              >
                <X className="w-3.5 h-3.5 text-muted-foreground" />
              </Button>
            </div>

            <div>
              <Label htmlFor="node-title">Node title</Label>
              <Input
                id="node-title"
                value={selectedNode.data.label}
                onChange={(e) => handleUpdateLabel(e.target.value)}
                className="font-medium"
              />
            </div>

            <div className="border-t border-border" />

            {selectedNode.data.nodeType === 'trigger' && (
              <>
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <Label>Trigger type</Label>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setIsChangingTrigger(true)}
                    >
                      <Edit className="w-3 h-3 mr-1" />
                      Change
                    </Button>
                  </div>
                  <div className="p-2 rounded-md bg-muted text-sm">
                    {selectedNode.data.triggerConfig?.type ? (
                      <span className="capitalize">
                        {selectedNode.data.triggerConfig.type.replace('-', ' ')}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Not configured</span>
                    )}
                  </div>
                </div>

                {renderTriggerForm()}
              </>
            )}

            {selectedNode.data.nodeType === 'action' && selectedNode.data.actionConfig && (() => {
              const config = selectedNode.data.actionConfig;
              const handleUpdateActionConfig = (field: string, value: unknown) => {
                if (selectedNodeId) {
                  updateNode(selectedNodeId, {
                    data: {
                      ...selectedNode.data,
                      actionConfig: {
                        ...selectedNode.data.actionConfig!,
                        [field]: value
                      }
                    }
                  });
                }
              };

              const renderNodeIdSelect = (
                id: string,
                value: string | undefined,
                onChange: (value: string) => void,
                placeholder: string
              ) => {
                const otherNodes = (activeFlow?.nodes || []).filter((n) => n.id !== selectedNodeId);
                const currentValue = value || '';
                const isMissing = currentValue && !otherNodes.some((n) => n.id === currentValue);
                return (
                  <Select value={currentValue} onValueChange={onChange}>
                    <SelectTrigger id={id}>
                      <SelectValue placeholder={placeholder} />
                    </SelectTrigger>
                    <SelectContent>
                      {isMissing && (
                        <SelectItem value={currentValue}>
                          {`Missing node: ${currentValue} (not found)`}
                        </SelectItem>
                      )}
                      {otherNodes.map((n) => (
                        <SelectItem key={n.id} value={n.id}>
                          {n.data.label || n.id}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                );
              };

              if (config.type === 'agent-run') {
                return (
                  <div className="space-y-3">
                    <Label weight="semibold" className="mb-2 block">Agent configuration</Label>
                    <div>
                      <Label htmlFor="agent-name" size="sm">Agent</Label>
                      <Combobox
                        options={agents}
                        value={config.agent_name || ''}
                        onValueChange={(v) => handleUpdateActionConfig('agent_name', v)}
                        placeholder={loadingAgents ? 'Loading...' : 'Select agent...'}
                        disabled={loadingAgents}
                        searchPlaceholder="Search agents..."
                        emptyText="No agent found."
                        linkTo={linkRoutes.agent}
                      />
                    </div>
                    <div>
                      <div className="flex justify-between items-center mb-1">
                        <Label htmlFor="prompt-template" size="sm">Prompt template</Label>
                        <VariablePicker onSelect={(v) => {
                          const current = config.prompt_template || '';
                          handleUpdateActionConfig('prompt_template', current + (current.length && !current.endsWith(' ') ? ' ' : '') + v);
                        }} />
                      </div>
                      <Textarea
                        id="prompt-template"
                        className="min-h-[80px] w-full"
                        value={config.prompt_template || ''}
                        onChange={(e) => handleUpdateActionConfig('prompt_template', e.target.value)}
                        placeholder="Enter prompt template. Use {{context.key}} for variables."
                      />
                    </div>
                    <div>
                      <Label htmlFor="save-key" size="sm">Save response to</Label>
                      <Input
                        id="save-key"
                        value={config.save_response_to_context || ''}
                        onChange={(e) => handleUpdateActionConfig('save_response_to_context', e.target.value)}
                        placeholder="e.g., agent_response"
                      />
                    </div>
                    <div>
                      <Label htmlFor="agent-run-conv-mode" className="text-xs">Conversation Mode</Label>
                      <Select
                        value={(config as { conversation_mode?: string }).conversation_mode || 'flow_shared'}
                        onValueChange={(value) => handleUpdateActionConfig('conversation_mode', value)}
                      >
                        <SelectTrigger id="agent-run-conv-mode">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="flow_shared">Flow Shared (Default)</SelectItem>
                          <SelectItem value="isolated">Isolated (No history)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                );
              }

              if (config.type === 'tool-call') {
                return (
                  <div className="space-y-3">
                    <Label weight="semibold" className="mb-2 block">Tool configuration</Label>
                    {flowToolsDegraded && (
                      <div className="text-[10px] text-muted-foreground p-2 bg-muted/30 rounded-md border border-dashed">
                        MCP tools aren't available right now — showing built-in tools only.
                      </div>
                    )}
                    <div>
                      <Label htmlFor="tool-name" size="sm">Tool</Label>
                      <Combobox
                        options={tools}
                        value={config.tool_name || ''}
                        onValueChange={(v) => {
                          const flowTool = flowToolsByName[v];
                          handleUpdateActionConfig('tool_name', v);
                          handleUpdateActionConfig('mcp_server', flowTool?.mcp_server ?? null);
                        }}
                        placeholder={loadingTools ? 'Loading...' : 'Select tool...'}
                        disabled={loadingTools}
                        searchPlaceholder="Search tools..."
                        emptyText="No tool found."
                      />
                    </div>
                    <div>
                      <Label size="sm" weight="semibold" className="mb-2 block">Arguments</Label>
                      {loadingToolDetails ? (
                        <div className="text-sm text-muted-foreground p-2 bg-muted/30 rounded-md">Loading parameters...</div>
                      ) : !selectedToolDetails ? (
                        <div className="text-sm text-muted-foreground p-2 bg-muted/30 rounded-md">Select a tool to view parameters</div>
                      ) : selectedToolDetails.params_json_schema ? (
                        <div className="p-3 bg-muted/20 border rounded-md">
                          <JsonSchemaForm
                            schema={selectedToolDetails.params_json_schema}
                            value={config.args || {}}
                            onChange={(next) => handleUpdateActionConfig('args', next)}
                          />
                        </div>
                      ) : selectedToolDetails.parameters && selectedToolDetails.parameters.length > 0 ? (
                        <div className="space-y-3 p-3 bg-muted/20 border rounded-md">
                          {selectedToolDetails.parameters.map((param: ToolParameter) => {
                            const currentArgs = config.args || {};
                            return (
                              <div key={param.fieldname}>
                                <div className="flex justify-between items-center mb-1">
                                  <Label htmlFor={`arg-${param.fieldname}`} size="sm">
                                    {param.label || param.fieldname} {param.required ? <span className="text-destructive">*</span> : ''}
                                  </Label>
                                  <div className="flex items-center gap-2">
                                    <span className="text-[10px] text-muted-foreground font-mono">{param.type}</span>
                                    {['Data', 'Small Text', 'Long Text'].includes(param.type) && (
                                      <VariablePicker onSelect={(v) => {
                                        const current = (currentArgs[param.fieldname] as string) || '';
                                        handleUpdateActionConfig('args', {
                                          ...currentArgs,
                                          [param.fieldname]: current + (current.length && !current.endsWith(' ') ? ' ' : '') + v
                                        });
                                      }} />
                                    )}
                                  </div>
                                </div>
                                <Input
                                  id={`arg-${param.fieldname}`}
                                  value={(currentArgs[param.fieldname] as string) || ''}
                                  onChange={(e) => {
                                    handleUpdateActionConfig('args', {
                                      ...currentArgs,
                                      [param.fieldname]: e.target.value
                                    });
                                  }}
                                  placeholder={param.description || `Enter ${param.fieldname}...`}
                                  size="sm"
                                  className="font-mono"
                                />
                                {param.description && (
                                  <p className="text-[10px] text-muted-foreground mt-1">{param.description}</p>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="text-sm text-muted-foreground p-2 bg-muted/30 rounded-md">This tool has no requested parameters.</div>
                      )}
                    </div>
                    <div>
                      <Label htmlFor="save-result" size="sm">Save result to context</Label>
                      <Input
                        id="save-result"
                        value={(config.output?.save_result_to_context) || ''}
                        onChange={(e) => handleUpdateActionConfig('output', { ...(config.output || {}), save_result_to_context: e.target.value })}
                        placeholder="e.g., tool_result"
                      />
                    </div>
                    <div>
                      <Label htmlFor="tool-call-agent" className="text-xs">Attributed Agent (optional)</Label>
                      <Combobox
                        options={agents}
                        value={(config as { agent_name?: string }).agent_name || ''}
                        onValueChange={(v) => handleUpdateActionConfig('agent_name', v)}
                        placeholder={loadingAgents ? 'Loading...' : 'Select agent (optional)...'}
                        disabled={loadingAgents}
                        searchPlaceholder="Search agents..."
                        emptyText="No agent found."
                        linkTo={linkRoutes.agent}
                      />
                      <p className="text-[10px] text-muted-foreground mt-1">
                        Used only for audit attribution on the Agent Run record; does not affect tool execution.
                      </p>
                    </div>
                  </div>
                );
              }

              if (config.type === 'router') {
                return (
                  <div className="space-y-3">
                    <Label weight="semibold" className="mb-2 block">LLM router configuration</Label>
                    <div className="text-xs text-muted-foreground p-2 bg-muted/30 rounded-md mb-2">
                      Connect edges from this node to other nodes. The LLM will use edge labels to decide where to route.
                    </div>
                    <div>
                      <Label htmlFor="router-agent" size="sm">Routing agent</Label>
                      <Combobox
                        options={agents}
                        value={config.router_agent_name || ''}
                        onValueChange={(v) => handleUpdateActionConfig('router_agent_name', v)}
                        placeholder={loadingAgents ? 'Loading...' : 'Select routing agent...'}
                        disabled={loadingAgents}
                        searchPlaceholder="Search agents..."
                        emptyText="No agent found."
                        linkTo={linkRoutes.agent}
                      />
                    </div>
                    <div>
                      <Label htmlFor="conv-mode" size="sm">Conversation mode</Label>
                      <Select
                        value={config.conversation_mode || 'flow_shared'}
                        onValueChange={(value) => handleUpdateActionConfig('conversation_mode', value)}
                      >
                        <SelectTrigger id="conv-mode">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="flow_shared">Flow shared (default)</SelectItem>
                          <SelectItem value="isolated">Isolated (no history)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs font-semibold">Context Injection</Label>
                      {(() => {
                        const inject = (config as { inject?: Record<string, boolean> }).inject || {};
                        const updateInject = (field: string, value: boolean) => {
                          handleUpdateActionConfig('inject', { ...inject, [field]: value });
                        };
                        return (
                          <>
                            <div className="flex items-center gap-2">
                              <Checkbox
                                id="inject-include-context"
                                checked={inject.include_context ?? true}
                                onCheckedChange={(checked) => updateInject('include_context', checked === true)}
                              />
                              <Label htmlFor="inject-include-context" className="text-xs font-normal cursor-pointer">
                                Include flow context
                              </Label>
                            </div>
                            <div className="flex items-center gap-2">
                              <Checkbox
                                id="inject-include-last-result"
                                checked={inject.include_last_node_result ?? true}
                                onCheckedChange={(checked) => updateInject('include_last_node_result', checked === true)}
                              />
                              <Label htmlFor="inject-include-last-result" className="text-xs font-normal cursor-pointer">
                                Include last node result
                              </Label>
                            </div>
                            <div className="flex items-center gap-2">
                              <Checkbox
                                id="inject-include-candidates"
                                checked={inject.include_candidates ?? true}
                                onCheckedChange={(checked) => updateInject('include_candidates', checked === true)}
                              />
                              <Label htmlFor="inject-include-candidates" className="text-xs font-normal cursor-pointer">
                                Include routing candidates
                              </Label>
                            </div>
                          </>
                        );
                      })()}
                    </div>
                  </div>
                );
              }

              if (config.type === 'human.approval') {
                const approvalType = config.approval_type || 'role';
                const approverUsers = (config as { approver_users?: string[] | string }).approver_users;
                return (
                  <div className="space-y-3">
                    <Label weight="semibold" className="mb-2 block">Human approval configuration</Label>
                    <div>
                      <Label htmlFor="approval-title" size="sm">Title</Label>
                      <Input
                        id="approval-title"
                        value={config.title || ''}
                        onChange={(e) => handleUpdateActionConfig('title', e.target.value)}
                        placeholder="e.g., Approve Invoice #INV-001"
                      />
                    </div>
                    <div>
                      <Label htmlFor="approval-instructions" size="sm">Instructions</Label>
                      <Textarea
                        id="approval-instructions"
                        className="min-h-[60px] w-full"
                        value={config.instructions || ''}
                        onChange={(e) => handleUpdateActionConfig('instructions', e.target.value)}
                        placeholder="Detailed instructions for the approver"
                      />
                    </div>
                    <div>
                      <div className="flex justify-between items-center mb-1">
                        <Label htmlFor="context-summary" size="sm">Context summary</Label>
                        <VariablePicker onSelect={(v) => {
                          const current = config.context_summary || '';
                          handleUpdateActionConfig('context_summary', current + (current.length && !current.endsWith(' ') ? ' ' : '') + v);
                        }} />
                      </div>
                      <Textarea
                        id="context-summary"
                        className="min-h-[50px] w-full"
                        value={config.context_summary || ''}
                        onChange={(e) => handleUpdateActionConfig('context_summary', e.target.value)}
                        placeholder="e.g., Please review invoice for {{customer}} worth {{amount}}"
                      />
                    </div>
                    <div>
                      <Label htmlFor="approval-type" size="sm">Approval type</Label>
                      <Select
                        value={approvalType}
                        onValueChange={(value) => handleUpdateActionConfig('approval_type', value)}
                      >
                        <SelectTrigger id="approval-type">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="role">By role</SelectItem>
                          <SelectItem value="user">By user</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    {approvalType === 'role' && (
                      <div>
                        <Label htmlFor="approver-role" size="sm">Approver role</Label>
                        <Combobox
                          options={roles}
                          value={(config as { approver_role?: string }).approver_role || ''}
                          onValueChange={(v) => handleUpdateActionConfig('approver_role', v)}
                          placeholder={loadingRoles ? 'Loading roles...' : 'Select role...'}
                          disabled={loadingRoles}
                          searchPlaceholder="Search roles..."
                          emptyText="No role found."
                        />
                      </div>
                    )}
                    {approvalType === 'user' && (
                      <div>
                        <Label htmlFor="approver-users" size="sm">Approver users (comma-separated emails)</Label>
                        <Input
                          id="approver-users"
                          value={Array.isArray(approverUsers)
                            ? approverUsers.join(', ')
                            : approverUsers || ''}
                          onChange={(e) => handleUpdateActionConfig('approver_users',
                            e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean)
                          )}
                          placeholder="e.g., manager@company.com, cfo@company.com"
                        />
                      </div>
                    )}
                    <div>
                      <Label htmlFor="ref-doctype" size="sm">Reference DocType (Optional)</Label>
                      <Combobox
                        options={docTypes}
                        value={config.reference_doctype || ''}
                        onValueChange={(v) => handleUpdateActionConfig('reference_doctype', v)}
                        placeholder="e.g., Sales Invoice"
                        searchPlaceholder="Search DocType..."
                        emptyText="No DocType found."
                      />
                    </div>
                    <div>
                      <div className="flex justify-between items-center mb-1">
                        <Label htmlFor="ref-name" size="sm">Reference document name</Label>
                        <VariablePicker onSelect={(v) => {
                          const current = config.reference_name || '';
                          handleUpdateActionConfig('reference_name', current + (current.length && !current.endsWith(' ') ? ' ' : '') + v);
                        }} />
                      </div>
                      <Input
                        id="ref-name"
                        value={config.reference_name || ''}
                        onChange={(e) => handleUpdateActionConfig('reference_name', e.target.value)}
                        placeholder="e.g., {{invoice.name}}"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label htmlFor="save-decision" size="sm">Store decision in context key</Label>
                      <Input
                        id="save-decision"
                        value={config.store_decision_in_context || ''}
                        onChange={(e) => handleUpdateActionConfig('store_decision_in_context', e.target.value)}
                        placeholder="e.g., approval_result"
                      />
                    </div>
                  </div>
                );
              }

              if (config.type === 'condition') {
                return (
                  <div className="space-y-3">
                    <Label weight="semibold" className="mb-2 block">Condition (IF) configuration</Label>
                    <div className="text-xs text-muted-foreground p-2 bg-muted/30 rounded-md mb-2">
                      Evaluates a boolean expression against context. Routes to True or False branch node.
                    </div>
                    <div>
                      <div className="flex justify-between items-center mb-1">
                        <Label htmlFor="condition-expr" size="sm">Expression</Label>
                        <VariablePicker onSelect={(v) => {
                          const current = config.expression || '';
                          handleUpdateActionConfig('expression', current + (current.length && !current.endsWith(' ') ? ' ' : '') + v);
                        }} />
                      </div>
                      <Textarea
                        id="condition-expr"
                        className="min-h-[60px] w-full font-mono"
                        value={config.expression || ''}
                        onChange={(e) => handleUpdateActionConfig('expression', e.target.value)}
                        placeholder='context["status"] == "approved"'
                      />
                    </div>
                    <div>
                      <Label htmlFor="true-node" size="sm">True branch (node ID)</Label>
                      {renderNodeIdSelect('true-node', config.true_node, (v) => handleUpdateActionConfig('true_node', v), 'Select node for True branch...')}
                    </div>
                    <div>
                      <Label htmlFor="false-node" size="sm">False branch (node ID)</Label>
                      {renderNodeIdSelect('false-node', config.false_node, (v) => handleUpdateActionConfig('false_node', v), 'Select node for False branch...')}
                    </div>
                  </div>
                );
              }

              if (config.type === 'http-request') {
                return (
                  <div className="space-y-3">
                    <Label weight="semibold" className="mb-2 block">HTTP request configuration</Label>
                    <div>
                      <div className="flex justify-between items-center mb-1">
                        <Label htmlFor="http-url" size="sm">URL</Label>
                        <VariablePicker onSelect={(v) => {
                          const current = config.url || '';
                          handleUpdateActionConfig('url', current + (current.length && !current.endsWith(' ') ? ' ' : '') + v);
                        }} />
                      </div>
                      <Input
                        id="http-url"
                        value={config.url || ''}
                        onChange={(e) => handleUpdateActionConfig('url', e.target.value)}
                        placeholder="https://api.example.com/endpoint"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label htmlFor="http-method" size="sm">Method</Label>
                      <Select
                        value={config.method || 'GET'}
                        onValueChange={(value) => handleUpdateActionConfig('method', value)}
                      >
                        <SelectTrigger id="http-method">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="GET">GET</SelectItem>
                          <SelectItem value="POST">POST</SelectItem>
                          <SelectItem value="PUT">PUT</SelectItem>
                          <SelectItem value="PATCH">PATCH</SelectItem>
                          <SelectItem value="DELETE">DELETE</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label htmlFor="http-headers" size="sm">Headers (JSON)</Label>
                      <Textarea
                        id="http-headers"
                        className="min-h-[50px] w-full font-mono"
                        value={typeof config.headers === 'object'
                          ? JSON.stringify(config.headers, null, 2)
                          : config.headers || ''}
                        onChange={(e) => {
                          try {
                            handleUpdateActionConfig('headers', JSON.parse(e.target.value));
                          } catch {
                            handleUpdateActionConfig('headers', e.target.value);
                          }
                        }}
                        placeholder='{"Authorization": "Bearer {{token}}"}'
                      />
                    </div>
                    <div>
                      <Label htmlFor="http-body" size="sm">Body</Label>
                      <Textarea
                        id="http-body"
                        className="min-h-[60px] w-full font-mono"
                        value={typeof config.body === 'object'
                          ? JSON.stringify(config.body, null, 2)
                          : config.body || ''}
                        onChange={(e) => {
                          try {
                            handleUpdateActionConfig('body', JSON.parse(e.target.value));
                          } catch {
                            handleUpdateActionConfig('body', e.target.value);
                          }
                        }}
                        placeholder='{"key": "{{context.value}}"}'
                      />
                    </div>
                    <div>
                      <Label htmlFor="http-timeout" size="sm">Timeout (seconds)</Label>
                      <Input
                        id="http-timeout"
                        type="number"
                        min={1}
                        max={300}
                        value={config.timeout || 30}
                        onChange={(e) => handleUpdateActionConfig('timeout', parseInt(e.target.value))}
                      />
                    </div>
                    <div>
                      <Label htmlFor="http-save" size="sm">Save result to context</Label>
                      <Input
                        id="http-save"
                        value={config.save_result_to_context || ''}
                        onChange={(e) => handleUpdateActionConfig('save_result_to_context', e.target.value)}
                        placeholder="e.g., api_response"
                      />
                    </div>
                  </div>
                );
              }

              if (config.type === 'transform') {
                const transformations = config.transformations || [];
                return (
                  <div className="space-y-3">
                    <Label weight="semibold" className="mb-2 block">Transform data configuration</Label>
                    <div className="text-xs text-muted-foreground p-2 bg-muted/30 rounded-md mb-2">
                      Map, copy, or template data between context variables.
                    </div>
                    {transformations.map((t, i: number) => (
                      <div key={i} className="p-3 bg-muted/20 border rounded-md space-y-2">
                        <div className="flex justify-between items-center">
                          <span className="text-xs font-medium">Transformation #{i + 1}</span>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-destructive"
                            onClick={() => {
                              const updated = [...transformations];
                              updated.splice(i, 1);
                              handleUpdateActionConfig('transformations', updated);
                            }}
                          >
                            ×
                          </Button>
                        </div>
                        <div>
                          <Label size="sm">Source field</Label>
                          <Input
                            value={t.source_field || ''}
                            onChange={(e) => {
                              const updated = [...transformations];
                              updated[i] = { ...t, source_field: e.target.value };
                              handleUpdateActionConfig('transformations', updated);
                            }}
                            placeholder="e.g., api_response.data"
                            size="sm"
                          />
                        </div>
                        <div>
                          <Label size="sm">Target field</Label>
                          <Input
                            value={t.target_field || ''}
                            onChange={(e) => {
                              const updated = [...transformations];
                              updated[i] = { ...t, target_field: e.target.value };
                              handleUpdateActionConfig('transformations', updated);
                            }}
                            placeholder="e.g., processed_data"
                            size="sm"
                          />
                        </div>
                        <div>
                          <Label size="sm">Operation</Label>
                          <Select
                            value={t.operation || 'copy'}
                            onValueChange={(v) => {
                              const updated = [...transformations];
                              updated[i] = { ...t, operation: v as 'copy' | 'map' | 'template' };
                              handleUpdateActionConfig('transformations', updated);
                            }}
                          >
                            <SelectTrigger size="sm">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="copy">Copy</SelectItem>
                              <SelectItem value="map">Map</SelectItem>
                              <SelectItem value="template">Template</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    ))}
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full"
                      onClick={() => {
                        handleUpdateActionConfig('transformations', [
                          ...transformations,
                          { source_field: '', target_field: '', operation: 'copy' }
                        ]);
                      }}
                    >
                      + Add Transformation
                    </Button>
                  </div>
                );
              }

              if (config.type === 'loop') {
                return (
                  <div className="space-y-3">
                    <Label weight="semibold" className="mb-2 block">Loop configuration</Label>
                    <div className="text-xs text-muted-foreground p-2 bg-muted/30 rounded-md mb-2">
                      Iterate over an array in context. Each iteration sets the current item and index.
                    </div>
                    <div>
                      <Label htmlFor="loop-iterate" size="sm">Iterate over (context key)</Label>
                      <Input
                        id="loop-iterate"
                        value={config.iterate_over || ''}
                        onChange={(e) => handleUpdateActionConfig('iterate_over', e.target.value)}
                        placeholder="e.g., items, users"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label htmlFor="loop-item" size="sm">Item variable</Label>
                      <Input
                        id="loop-item"
                        value={config.item_key || 'loop_item'}
                        onChange={(e) => handleUpdateActionConfig('item_key', e.target.value)}
                        placeholder="loop_item"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label htmlFor="loop-index" size="sm">Index variable</Label>
                      <Input
                        id="loop-index"
                        value={config.index_key || 'loop_index'}
                        onChange={(e) => handleUpdateActionConfig('index_key', e.target.value)}
                        placeholder="loop_index"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label htmlFor="loop-body" size="sm">Loop body node (node ID)</Label>
                      {renderNodeIdSelect('loop-body', config.loop_node, (v) => handleUpdateActionConfig('loop_node', v), 'Select node to execute per iteration...')}
                    </div>
                    <div>
                      <Label htmlFor="loop-done" size="sm">Done node (node ID)</Label>
                      {renderNodeIdSelect('loop-done', config.done_node, (v) => handleUpdateActionConfig('done_node', v), 'Select node to go to when done...')}
                    </div>
                    <div>
                      <Label htmlFor="loop-max" size="sm">Max iterations</Label>
                      <Input
                        id="loop-max"
                        type="number"
                        min={1}
                        max={10000}
                        value={config.max_iterations || 100}
                        onChange={(e) => handleUpdateActionConfig('max_iterations', parseInt(e.target.value))}
                      />
                    </div>
                  </div>
                );
              }

              // Fallback: show JSON for other action types
              return (
                <div>
                  <Label className="mb-2 block">Action configuration</Label>
                  <div className="p-3 rounded-md bg-muted/30 border border-border">
                    <code className="text-xs text-muted-foreground font-mono block overflow-x-auto">
                      {JSON.stringify(config, null, 2)}
                    </code>
                  </div>
                </div>
              );
            })()}
          </>
        ) : null}
      </div>

      {scheduleNextRun ? (
        <div className="border-t border-border p-3 bg-card flex items-center gap-2">
          <div className="flex items-center gap-1.5 min-w-0 rounded-md bg-paper px-2 py-1">
            <Clock className="w-3 h-3 text-muted-foreground shrink-0" />
            <span className="text-[12px] leading-none text-muted-foreground truncate">
              {scheduleNextRun}
            </span>
          </div>
        </div>
      ) : null}

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete node</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this node? Any edges connected to it will also be removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (selectedNodeId) {
                  deleteNode(selectedNodeId);
                  setShowDeleteConfirm(false);
                  onToggle();
                }
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {selectedNode && (
        <NodeSelectionModal
          open={isChangingTrigger}
          mode="trigger"
          onClose={() => setIsChangingTrigger(false)}
          onSaveTrigger={(config) => {
            if (selectedNodeId) {
              const iconMap: Record<string, string> = {
                webhook: 'Webhook',
                schedule: 'Clock',
                'doc-event': 'Database',
                'app-trigger': 'Mail'
              };

              updateNode(selectedNodeId, {
                data: {
                  ...selectedNode.data,
                  label: config.type === 'webhook' ? 'Webhook' :
                    config.type === 'schedule' ? 'Schedule' :
                      config.type === 'doc-event' ? 'Doc Event' :
                        'App Trigger',
                  icon: iconMap[config.type || 'webhook'],
                  configured: true,
                  triggerConfig: config
                }
              });
            }
            setIsChangingTrigger(false);
          }}
          initialTriggerConfig={selectedNode.data.triggerConfig}
        />
      )}
    </div>
  );
}
