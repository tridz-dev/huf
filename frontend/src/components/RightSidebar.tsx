import { toast } from 'sonner';
import { useState, useEffect } from 'react';
import { PanelRightClose, Settings, Edit, Trash2 } from 'lucide-react';
import { Input } from './ui/input';
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
import { ScheduleIntervalType, DocEventType } from '../types/flow.types';
import { getAgents, getDocTypes, getRoles } from '../services/agentApi';
import { getToolFunctions, getToolFunction, getFlowTools, type FlowTool } from '../services/toolApi';
import {
  getFlowTrigger,
  setFlowSchedule,
  setFlowDocEventTrigger,
  clearFlowTrigger,
  type FlowScheduledInterval,
  type FlowDocEvent,
  type FlowScheduleTrigger,
  type FlowDocEventTrigger as FlowDocEventTriggerRow,
} from '../services/flowApi';
import { VariablePicker } from './ui/VariablePicker';
import { JsonSchemaForm } from './JsonSchemaForm';

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
  const [width, setWidth] = useState(380);
  const [isResizing, setIsResizing] = useState(false);
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

  // Engine-backed Schedule / Doc Event trigger state. These reflect the real
  // Agent Trigger record the flow engine reads (see huf/ai/flow_api.py "Flow
  // Trigger APIs"); they are independent of the node's own triggerConfig,
  // which is display-only (see the comment above renderTriggerForm's
  // schedule/doc-event branches for why).
  const [scheduleTrigger, setScheduleTrigger] = useState<FlowScheduleTrigger | null>(null);
  const [scheduleTriggerLoading, setScheduleTriggerLoading] = useState(false);
  const [scheduleTriggerSaving, setScheduleTriggerSaving] = useState(false);
  const [scheduleTriggerError, setScheduleTriggerError] = useState<string | null>(null);
  // Local draft for the interval-count input. Writing on every keystroke fires
  // one API call per character ("12" -> a write for 1, then for 12), and those
  // can land out of order, so the persisted value is whichever request finishes
  // last rather than what the user typed. Persist on blur (or Enter) instead.
  const [intervalCountDraft, setIntervalCountDraft] = useState<string>('');

  const [docEventTrigger, setDocEventTrigger] = useState<FlowDocEventTriggerRow | null>(null);
  const [docEventTriggerLoading, setDocEventTriggerLoading] = useState(false);
  const [docEventTriggerSaving, setDocEventTriggerSaving] = useState(false);
  const [docEventTriggerError, setDocEventTriggerError] = useState<string | null>(null);

  const flowId = activeFlow?.id;
  const isScheduleTriggerSelected = selectedNode?.data.triggerConfig?.type === 'schedule';
  const isDocEventTriggerSelected = selectedNode?.data.triggerConfig?.type === 'doc-event';

  // Hydrate the real Schedule trigger from the backend when a Schedule
  // trigger node is selected on a saved flow.
  useEffect(() => {
    if (!isScheduleTriggerSelected || !flowId) {
      setScheduleTrigger(null);
      setScheduleTriggerError(null);
      return;
    }
    setScheduleTriggerLoading(true);
    setScheduleTriggerError(null);
    getFlowTrigger(flowId)
      .then((rows) => {
        const found = rows.find((r): r is FlowScheduleTrigger => r.trigger_type === 'Schedule');
        setScheduleTrigger(found || null);
      })
      .catch((err) => setScheduleTriggerError(err?.message || 'Failed to load schedule'))
      .finally(() => setScheduleTriggerLoading(false));
  }, [isScheduleTriggerSelected, flowId, selectedNode?.id]);

  // Hydrate the real Doc Event trigger from the backend when a Doc Event
  // trigger node is selected on a saved flow.
  useEffect(() => {
    if (!isDocEventTriggerSelected || !flowId) {
      setDocEventTrigger(null);
      setDocEventTriggerError(null);
      return;
    }
    setDocEventTriggerLoading(true);
    setDocEventTriggerError(null);
    getFlowTrigger(flowId)
      .then((rows) => {
        const found = rows.find((r): r is FlowDocEventTriggerRow => r.trigger_type === 'Doc Event');
        setDocEventTrigger(found || null);
      })
      .catch((err) => setDocEventTriggerError(err?.message || 'Failed to load doc event trigger'))
      .finally(() => setDocEventTriggerLoading(false));
  }, [isDocEventTriggerSelected, flowId, selectedNode?.id]);

  const handleSetSchedule = (scheduledInterval: FlowScheduledInterval, intervalCount: number) => {
    if (!flowId) return;
    setScheduleTriggerSaving(true);
    setScheduleTriggerError(null);
    setFlowSchedule(flowId, scheduledInterval, intervalCount, scheduleTrigger?.trigger_name)
      .then((row) => setScheduleTrigger(row))
      .catch((err) => setScheduleTriggerError(err?.message || 'Failed to save schedule'))
      .finally(() => setScheduleTriggerSaving(false));
  };

  const handleClearSchedule = () => {
    if (!scheduleTrigger) return;
    setScheduleTriggerSaving(true);
    setScheduleTriggerError(null);
    clearFlowTrigger(scheduleTrigger.trigger_name)
      .then(() => setScheduleTrigger(null))
      .catch((err) => setScheduleTriggerError(err?.message || 'Failed to remove schedule'))
      .finally(() => setScheduleTriggerSaving(false));
  };

  const handleSetDocEventTrigger = (referenceDoctype: string, docEvent: FlowDocEvent) => {
    if (!flowId || !referenceDoctype || !docEvent) return;
    setDocEventTriggerSaving(true);
    setDocEventTriggerError(null);
    setFlowDocEventTrigger(flowId, referenceDoctype, docEvent, undefined, docEventTrigger?.trigger_name)
      .then((row) => setDocEventTrigger(row))
      .catch((err) => setDocEventTriggerError(err?.message || 'Failed to save doc event trigger'))
      .finally(() => setDocEventTriggerSaving(false));
  };

  const handleClearDocEventTrigger = () => {
    if (!docEventTrigger) return;
    setDocEventTriggerSaving(true);
    setDocEventTriggerError(null);
    clearFlowTrigger(docEventTrigger.trigger_name)
      .then(() => setDocEventTrigger(null))
      .catch((err) => setDocEventTriggerError(err?.message || 'Failed to remove doc event trigger'))
      .finally(() => setDocEventTriggerSaving(false));
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  };

  useEffect(() => {
    if (!isResizing) return;
    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = window.innerWidth - e.clientX;
      setWidth(Math.min(Math.max(320, newWidth), 600));
    };
    const handleMouseUp = () => setIsResizing(false);
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

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
      const webhookUrl = `${window.location.origin}/api/method/huf.ai.flow_api.flow_webhook?flow_id=${activeFlow?.id || '{flow_id}'}&webhook_key=${config.auth || config.apiKey || '{key}'}`;

      return (
        <div className="space-y-3">
          <div>
            <Label className="text-xs">Webhook URL (Auto-generated)</Label>
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
            <Label htmlFor="webhook-auth" className="text-xs">Authentication Key (Optional)</Label>
            <Input
              id="webhook-auth"
              // fall back to the legacy `apiKey` name so keys saved before the
              // modal was canonicalised on `auth` remain visible and editable
              value={config.auth || config.apiKey || ''}
              onChange={(e) => handleUpdateTriggerConfig('auth', e.target.value)}
              placeholder="e.g. my-secret-key-123"
            />
          </div>
          <div>
            <Label htmlFor="method" className="text-xs">HTTP Method (Expected)</Label>
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
      // NOTE: intervalType/interval/cronExpression below are node-config-only
      // fields. The flow engine does NOT read them - it reads `cron`/
      // `scheduled_interval` off a real Agent Trigger record. They are kept
      // here purely so a flow authored before the engine wiring existed keeps
      // showing its old values (back-compat display), and because the
      // engine has no concept of "minutes" intervals or arbitrary cron
      // expressions (see valid_intervals in set_flow_schedule) so they can't
      // be losslessly promoted into the real control below. The "Runs..."
      // section below is the one that actually configures the engine.
      return (
        <>
          <div className="opacity-70">
            <Label htmlFor="interval-type" className="text-xs">Schedule Type (legacy display only)</Label>
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
                <SelectItem value="custom">Custom (Cron)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {config.intervalType !== 'custom' && (
            <div className="opacity-70">
              <Label htmlFor="interval" className="text-xs">Interval (legacy display only)</Label>
              <Input
                id="interval"
                type="number"
                min="1"
                value={config.interval || 1}
                onChange={(e) => handleUpdateTriggerConfig('interval', parseInt(e.target.value))}
              />
            </div>
          )}
          {config.intervalType === 'custom' && (
            <div className="opacity-70">
              <Label htmlFor="cron" className="text-xs">Cron Expression (legacy display only)</Label>
              <Input
                id="cron"
                value={config.cronExpression || ''}
                onChange={(e) => handleUpdateTriggerConfig('cronExpression', e.target.value)}
                placeholder="0 */6 * * *"
              />
            </div>
          )}

          <div className="border-t border-border pt-3 space-y-3">
            <Label className="text-xs font-medium">Runs on a schedule (engine)</Label>
            {!flowId ? (
              <p className="text-xs text-muted-foreground">Save the flow first to enable scheduling.</p>
            ) : (
              <>
                <div>
                  <Label htmlFor="engine-scheduled-interval" className="text-xs">Frequency</Label>
                  <Select
                    value={scheduleTrigger?.scheduled_interval || ''}
                    disabled={scheduleTriggerLoading || scheduleTriggerSaving}
                    onValueChange={(value) =>
                      handleSetSchedule(value as FlowScheduledInterval, scheduleTrigger?.interval_count || 1)
                    }
                  >
                    <SelectTrigger id="engine-scheduled-interval">
                      <SelectValue placeholder={scheduleTriggerLoading ? 'Loading...' : 'Select frequency...'} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Hourly">Hourly</SelectItem>
                      <SelectItem value="Daily">Daily</SelectItem>
                      <SelectItem value="Weekly">Weekly</SelectItem>
                      <SelectItem value="Monthly">Monthly</SelectItem>
                      <SelectItem value="Yearly">Yearly</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {scheduleTrigger && (
                  <div>
                    <Label htmlFor="engine-interval-count" className="text-xs">Every N intervals</Label>
                    <Input
                      id="engine-interval-count"
                      type="number"
                      min="1"
                      disabled={scheduleTriggerLoading || scheduleTriggerSaving}
                      value={intervalCountDraft !== '' ? intervalCountDraft : String(scheduleTrigger.interval_count || 1)}
                      onChange={(e) => setIntervalCountDraft(e.target.value)}
                      onBlur={() => {
                        if (intervalCountDraft === '') return;
                        const n = parseInt(intervalCountDraft) || 1;
                        setIntervalCountDraft('');
                        if (n !== (scheduleTrigger.interval_count || 1)) {
                          handleSetSchedule(scheduleTrigger.scheduled_interval, n);
                        }
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                      }}
                    />
                  </div>
                )}
                {scheduleTrigger && (
                  <div className="text-xs text-muted-foreground space-y-1">
                    <p>
                      Runs {scheduleTrigger.scheduled_interval.toLowerCase()}
                      {scheduleTrigger.interval_count > 1 ? ` (every ${scheduleTrigger.interval_count})` : ''}
                      {scheduleTrigger.next_execution ? ` · next run ${scheduleTrigger.next_execution}` : ''}
                    </p>
                    {scheduleTrigger.last_execution && (
                      <p>Last run {scheduleTrigger.last_execution}</p>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={scheduleTriggerSaving}
                      onClick={handleClearSchedule}
                    >
                      Remove schedule
                    </Button>
                  </div>
                )}
                {scheduleTriggerError && (
                  <p className="text-xs text-destructive">{scheduleTriggerError}</p>
                )}
              </>
            )}
          </div>
        </>
      );
    }

    if (config.type === 'doc-event') {
      // NOTE: doctype/event below are node-config-only fields, kept for
      // back-compat display; the engine does not read them. The engine
      // reads reference_doctype/doc_event off a real Agent Trigger record,
      // configured by the "Fires on a document event (engine)" section
      // below, which uses the actual doc_event values the Agent Trigger
      // doctype supports (see agent_trigger.json) rather than the
      // friendlier-but-lossy save/update/delete categories used here.
      return (
        <>
          <div className="opacity-70">
            <Label htmlFor="doctype" className="text-xs">Document Type (legacy display only)</Label>
            <Combobox
                        id="doctype"
              options={docTypes}
              value={config.doctype || ''}
              onValueChange={(v) => handleUpdateTriggerConfig('doctype', v)}
              placeholder={loadingDocTypes ? 'Loading...' : 'Select DocType...'}
              disabled={loadingDocTypes}
              searchPlaceholder="Search DocType..."
              emptyText="No DocType found."
            />
          </div>
          <div className="opacity-70">
            <Label htmlFor="event" className="text-xs">Event Type (legacy display only)</Label>
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
                <SelectItem value="before-save">Before Save</SelectItem>
                <SelectItem value="before-update">Before Update</SelectItem>
                <SelectItem value="before-delete">Before Delete</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="border-t border-border pt-3 space-y-3">
            <Label className="text-xs font-medium">Fires on a document event (engine)</Label>
            {!flowId ? (
              <p className="text-xs text-muted-foreground">Save the flow first to enable this trigger.</p>
            ) : (
              <>
                <div>
                  <Label htmlFor="engine-doctype" className="text-xs">Document Type (Engine)</Label>
                  <Combobox
                    id="engine-doctype"
                    options={docTypes}
                    value={docEventTrigger?.reference_doctype || ''}
                    onValueChange={(v) =>
                      handleSetDocEventTrigger(v, docEventTrigger?.doc_event || 'after_save')
                    }
                    placeholder={loadingDocTypes ? 'Loading...' : 'Select DocType...'}
                    disabled={loadingDocTypes || docEventTriggerLoading || docEventTriggerSaving}
                    searchPlaceholder="Search DocType..."
                    emptyText="No DocType found."
                  />
                </div>
                <div>
                  <Label htmlFor="engine-doc-event" className="text-xs">Event (Engine)</Label>
                  <Select
                    value={docEventTrigger?.doc_event || ''}
                    disabled={docEventTriggerLoading || docEventTriggerSaving || !docEventTrigger?.reference_doctype}
                    onValueChange={(value) =>
                      handleSetDocEventTrigger(docEventTrigger?.reference_doctype || '', value as FlowDocEvent)
                    }
                  >
                    <SelectTrigger id="engine-doc-event">
                      <SelectValue placeholder={docEventTriggerLoading ? 'Loading...' : 'Select event...'} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="before_insert">Before Insert</SelectItem>
                      <SelectItem value="after_insert">After Insert</SelectItem>
                      <SelectItem value="validate">Validate</SelectItem>
                      <SelectItem value="before_save">Before Save</SelectItem>
                      <SelectItem value="after_save">After Save</SelectItem>
                      <SelectItem value="before_submit">Before Submit</SelectItem>
                      <SelectItem value="on_submit">On Submit</SelectItem>
                      <SelectItem value="on_update">On Update</SelectItem>
                      <SelectItem value="after_submit">After Submit</SelectItem>
                      <SelectItem value="on_cancel">On Cancel</SelectItem>
                      <SelectItem value="before_rename">Before Rename</SelectItem>
                      <SelectItem value="after_rename">After Rename</SelectItem>
                      <SelectItem value="on_trash">On Trash</SelectItem>
                      <SelectItem value="after_delete">After Delete</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {docEventTrigger && (
                  <div className="text-xs text-muted-foreground space-y-1">
                    <p>
                      Fires on {docEventTrigger.doc_event} of {docEventTrigger.reference_doctype}
                    </p>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={docEventTriggerSaving}
                      onClick={handleClearDocEventTrigger}
                    >
                      Remove trigger
                    </Button>
                  </div>
                )}
                {docEventTriggerError && (
                  <p className="text-xs text-destructive">{docEventTriggerError}</p>
                )}
              </>
            )}
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

  return (
    <div
      className={cn(
        'relative bg-card flex flex-col',
        isSheet ? 'h-full' : 'h-screen border-l border-border',
      )}
      style={isSheet ? undefined : { width: `${width}px` }}
    >
      {!isSheet && (
      <div
        className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/50 transition-colors"
        onMouseDown={handleMouseDown}
      />
      )}

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
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
              <Label htmlFor="edge-label">Edge Label</Label>
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

            <div className="space-y-4">
              <div>
                <Label htmlFor="edge-type" className="text-xs">Edge Type</Label>
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
                    <SelectItem value="always">Always (Default)</SelectItem>
                    <SelectItem value="on_success">On Success</SelectItem>
                    <SelectItem value="on_failure">On Failure</SelectItem>
                    <SelectItem value="expression">Expression</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {selectedEdge.data?.edgeType === 'expression' && (
                <div>
                  <Label htmlFor="edge-expr" className="text-xs">Condition Expression</Label>
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
                <Label htmlFor="edge-priority" className="text-xs">Priority</Label>
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
                <Label htmlFor="edge-outcome" className="text-xs">Approval Outcome</Label>
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
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="text-sm font-semibold">{selectedNode.data.label}</div>
                <span className="text-xs text-muted-foreground">({selectedNode.data.nodeType})</span>
              </div>
            </div>

            <div>
              <Label htmlFor="node-title">Node Title</Label>
              <Input
                id="node-title"
                value={selectedNode.data.label}
                onChange={(e) => handleUpdateLabel(e.target.value)}
                className="font-medium"
              />
            </div>

            {selectedNode.data.nodeType === 'trigger' && (
              <>
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <Label>Trigger Type</Label>
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
              // NOTE: this spreads actionConfig from the current render's closure,
              // so two calls fired back-to-back both build on the SAME stale base
              // and the second silently discards the first's field. Use
              // handleUpdateActionConfigMany when setting more than one key.
              const handleUpdateActionConfig = (field: string, value: unknown) => {
                handleUpdateActionConfigMany({ [field]: value });
              };

              /** Apply several config fields in ONE update. */
              const handleUpdateActionConfigMany = (patch: Record<string, unknown>) => {
                if (selectedNodeId) {
                  updateNode(selectedNodeId, {
                    data: {
                      ...selectedNode.data,
                      actionConfig: {
                        ...selectedNode.data.actionConfig!,
                        ...patch
                      }
                    }
                  });
                }
              };

              // True when `val` is a non-empty string that failed JSON.parse — used to
              // surface a non-blocking inline warning without discarding the raw text.
              const isInvalidJsonString = (val: unknown): boolean => {
                if (typeof val !== 'string' || val.trim() === '') return false;
                try {
                  JSON.parse(val);
                  return false;
                } catch {
                  return true;
                }
              };

              // Ancestor ids (nodes that can reach `targetId` via edges) — selecting one of
              // these as a branch target routes execution back upstream, i.e. a cycle.
              const computeAncestorIds = (targetId: string | null | undefined): Set<string> => {
                const edges = activeFlow?.edges || [];
                const visited = new Set<string>();
                if (!targetId) return visited;
                const queue = [targetId];
                while (queue.length) {
                  const cur = queue.shift()!;
                  for (const e of edges) {
                    if (e.target === cur && e.source && !visited.has(e.source)) {
                      visited.add(e.source);
                      queue.push(e.source);
                    }
                  }
                }
                return visited;
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
                const ancestorIds = computeAncestorIds(selectedNodeId);

                // Disambiguate options that share a display label (e.g. two "Transform
                // Data" nodes) by appending a short id suffix — only when needed, so
                // unique labels stay unchanged.
                const labelCounts = otherNodes.reduce((acc, n) => {
                  const label = n.data.label || n.id;
                  acc[label] = (acc[label] || 0) + 1;
                  return acc;
                }, {} as Record<string, number>);

                const describeNode = (n: (typeof otherNodes)[number]) => {
                  const label = n.data.label || n.id;
                  const isDuplicate = labelCounts[label] > 1;
                  const shortId = n.id.length > 8 ? `${n.id.slice(0, 8)}…` : n.id;
                  const base = isDuplicate ? `${label} · ${shortId}` : label;
                  return ancestorIds.has(n.id) ? `${base}  ↑ upstream — creates a loop` : base;
                };

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
                          {describeNode(n)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                );
              };

              if (config.type === 'agent-run') {
                return (
                  <div className="space-y-3">
                    <Label className="mb-2 block text-sm font-semibold">Agent Configuration</Label>
                    <div>
                      <Label htmlFor="agent-name" className="text-xs">Agent</Label>
                      <Combobox
                        id="agent-name"
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
                        <Label htmlFor="prompt-template" className="text-xs">Prompt Template</Label>
                        <VariablePicker onSelect={(v) => {
                          const current = config.prompt_template || '';
                          handleUpdateActionConfig('prompt_template', current + (current.length && !current.endsWith(' ') ? ' ' : '') + v);
                        }} />
                      </div>
                      <textarea
                        id="prompt-template"
                        className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={config.prompt_template || ''}
                        onChange={(e) => handleUpdateActionConfig('prompt_template', e.target.value)}
                        placeholder="Enter prompt template. Use {{context.key}} for variables."
                      />
                    </div>
                    <div>
                      <Label htmlFor="save-key" className="text-xs">Save Response To</Label>
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
                    <Label className="mb-2 block text-sm font-semibold">Tool Configuration</Label>
                    {flowToolsDegraded && (
                      <div className="text-[10px] text-muted-foreground p-2 bg-muted/30 rounded-md border border-dashed">
                        MCP tools aren't available right now — showing built-in tools only.
                      </div>
                    )}
                    <div>
                      <Label htmlFor="tool-name" className="text-xs">Tool</Label>
                      <Combobox
                        id="tool-name"
                        options={tools}
                        value={config.tool_name || ''}
                        onValueChange={(v) => {
                          const flowTool = flowToolsByName[v];
                          // Must be ONE update: two sequential calls both spread the
                          // same stale actionConfig, so the second would drop tool_name
                          // and the picker would silently reset to "Select tool...".
                          handleUpdateActionConfigMany({
                            tool_name: v,
                            mcp_server: flowTool?.mcp_server ?? null,
                          });
                        }}
                        placeholder={loadingTools ? 'Loading...' : 'Select tool...'}
                        disabled={loadingTools}
                        searchPlaceholder="Search tools..."
                        emptyText="No tool found."
                      />
                    </div>
                    <div>
                      <Label className="text-xs font-semibold mb-2 block">Arguments</Label>
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
                                  <Label htmlFor={`arg-${param.fieldname}`} className="text-xs font-medium">
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
                                  className="h-8 text-xs font-mono"
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
                      <Label htmlFor="save-result" className="text-xs">Save Result To Context</Label>
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
                        id="tool-call-agent"
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
                    <Label className="mb-2 block text-sm font-semibold">LLM Router Configuration</Label>
                    <div className="text-xs text-muted-foreground p-2 bg-muted/30 rounded-md mb-2">
                      Connect edges from this node to other nodes. The LLM will use edge labels to decide where to route.
                    </div>
                    <div>
                      <Label htmlFor="router-agent" className="text-xs">Routing Agent</Label>
                      <Combobox
                        id="router-agent"
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
                      <Label htmlFor="conv-mode" className="text-xs">Conversation Mode</Label>
                      <Select
                        value={config.conversation_mode || 'flow_shared'}
                        onValueChange={(value) => handleUpdateActionConfig('conversation_mode', value)}
                      >
                        <SelectTrigger id="conv-mode">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="flow_shared">Flow Shared (Default)</SelectItem>
                          <SelectItem value="isolated">Isolated (No history)</SelectItem>
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
                    <Label className="mb-2 block text-sm font-semibold">Human Approval Configuration</Label>
                    <div>
                      <Label htmlFor="approval-title" className="text-xs">Title</Label>
                      <Input
                        id="approval-title"
                        value={config.title || ''}
                        onChange={(e) => handleUpdateActionConfig('title', e.target.value)}
                        placeholder="e.g., Approve Invoice #INV-001"
                      />
                    </div>
                    <div>
                      <Label htmlFor="approval-instructions" className="text-xs">Instructions</Label>
                      <textarea
                        id="approval-instructions"
                        className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={config.instructions || ''}
                        onChange={(e) => handleUpdateActionConfig('instructions', e.target.value)}
                        placeholder="Detailed instructions for the approver"
                      />
                    </div>
                    <div>
                      <div className="flex justify-between items-center mb-1">
                        <Label htmlFor="context-summary" className="text-xs">Context Summary</Label>
                        <VariablePicker onSelect={(v) => {
                          const current = config.context_summary || '';
                          handleUpdateActionConfig('context_summary', current + (current.length && !current.endsWith(' ') ? ' ' : '') + v);
                        }} />
                      </div>
                      <textarea
                        id="context-summary"
                        className="flex min-h-[50px] w-full rounded-md border border-input bg-background px-3 py-2 text-xs ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={config.context_summary || ''}
                        onChange={(e) => handleUpdateActionConfig('context_summary', e.target.value)}
                        placeholder="e.g., Please review invoice for {{customer}} worth {{amount}}"
                      />
                    </div>
                    <div>
                      <Label htmlFor="approval-type" className="text-xs">Approval Type</Label>
                      <Select
                        value={approvalType}
                        onValueChange={(value) => handleUpdateActionConfig('approval_type', value)}
                      >
                        <SelectTrigger id="approval-type">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="role">By Role</SelectItem>
                          <SelectItem value="user">By User</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    {approvalType === 'role' && (
                      <div>
                        <Label htmlFor="approver-role" className="text-xs">Approver Role</Label>
                        <Combobox
                        id="approver-role"
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
                        <Label htmlFor="approver-users" className="text-xs">Approver Users (comma-separated emails)</Label>
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
                      <Label htmlFor="ref-doctype" className="text-xs">Reference DocType (Optional)</Label>
                      <Combobox
                        id="ref-doctype"
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
                        <Label htmlFor="ref-name" className="text-xs">Reference Document Name</Label>
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
                      <Label htmlFor="save-decision" className="text-xs">Store Decision in Context Key</Label>
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
                    <Label className="mb-2 block text-sm font-semibold">Condition (IF) Configuration</Label>
                    <div className="text-xs text-muted-foreground p-2 bg-muted/30 rounded-md mb-2">
                      Evaluates a boolean expression against context. Routes to True or False branch node.
                    </div>
                    <div>
                      <div className="flex justify-between items-center mb-1">
                        <Label htmlFor="condition-expr" className="text-xs">Expression</Label>
                        <VariablePicker onSelect={(v) => {
                          const current = config.expression || '';
                          handleUpdateActionConfig('expression', current + (current.length && !current.endsWith(' ') ? ' ' : '') + v);
                        }} />
                      </div>
                      <textarea
                        id="condition-expr"
                        className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={config.expression || ''}
                        onChange={(e) => handleUpdateActionConfig('expression', e.target.value)}
                        placeholder='context["status"] == "approved"'
                      />
                    </div>
                    <div>
                      <Label htmlFor="true-node" className="text-xs">True Branch</Label>
                      {renderNodeIdSelect('true-node', config.true_node, (v) => handleUpdateActionConfig('true_node', v), 'Select node for True branch...')}
                    </div>
                    <div>
                      <Label htmlFor="false-node" className="text-xs">False Branch</Label>
                      {renderNodeIdSelect('false-node', config.false_node, (v) => handleUpdateActionConfig('false_node', v), 'Select node for False branch...')}
                    </div>
                  </div>
                );
              }

              if (config.type === 'http-request') {
                return (
                  <div className="space-y-3">
                    <Label className="mb-2 block text-sm font-semibold">HTTP Request Configuration</Label>
                    <div>
                      <div className="flex justify-between items-center mb-1">
                        <Label htmlFor="http-url" className="text-xs">URL</Label>
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
                      <Label htmlFor="http-method" className="text-xs">Method</Label>
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
                      <Label htmlFor="http-headers" className="text-xs">Headers (JSON)</Label>
                      <textarea
                        id="http-headers"
                        className="flex min-h-[50px] w-full rounded-md border border-input bg-background px-3 py-2 text-xs font-mono ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
                      {isInvalidJsonString(config.headers) && (
                        <p className="text-[10px] text-destructive mt-1">
                          Not valid JSON — saved as plain text.
                        </p>
                      )}
                    </div>
                    <div>
                      <Label htmlFor="http-body" className="text-xs">Body</Label>
                      <textarea
                        id="http-body"
                        className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-xs font-mono ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
                      {isInvalidJsonString(config.body) && (
                        <p className="text-[10px] text-destructive mt-1">
                          Not valid JSON — saved as plain text.
                        </p>
                      )}
                    </div>
                    <div>
                      <Label htmlFor="http-timeout" className="text-xs">Timeout (seconds)</Label>
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
                      <Label htmlFor="http-save" className="text-xs">Save Result To Context</Label>
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
                    <Label className="mb-2 block text-sm font-semibold">Transform Data Configuration</Label>
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
                          <Label htmlFor={`transform-${i}-source`} className="text-[10px]">Source Field</Label>
                          <Input
                            id={`transform-${i}-source`}
                            value={t.source_field || ''}
                            onChange={(e) => {
                              const updated = [...transformations];
                              updated[i] = { ...t, source_field: e.target.value };
                              handleUpdateActionConfig('transformations', updated);
                            }}
                            placeholder="e.g., api_response.data"
                            className="h-7 text-xs"
                          />
                        </div>
                        <div>
                          <Label htmlFor={`transform-${i}-target`} className="text-[10px]">Target Field</Label>
                          <Input
                            id={`transform-${i}-target`}
                            value={t.target_field || ''}
                            onChange={(e) => {
                              const updated = [...transformations];
                              updated[i] = { ...t, target_field: e.target.value };
                              handleUpdateActionConfig('transformations', updated);
                            }}
                            placeholder="e.g., processed_data"
                            className="h-7 text-xs"
                          />
                        </div>
                        <div>
                          <Label htmlFor={`transform-${i}-operation`} className="text-[10px]">Operation</Label>
                          <Select
                            value={t.operation || 'copy'}
                            onValueChange={(v) => {
                              const updated = [...transformations];
                              updated[i] = { ...t, operation: v as 'copy' | 'map' | 'template' };
                              handleUpdateActionConfig('transformations', updated);
                            }}
                          >
                            <SelectTrigger id={`transform-${i}-operation`} className="h-7 text-xs">
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
                    <Label className="mb-2 block text-sm font-semibold">Loop Configuration</Label>
                    <div className="text-xs text-muted-foreground p-2 bg-muted/30 rounded-md mb-2">
                      Iterate over an array in context. Each iteration sets the current item and index.
                    </div>
                    <div>
                      <Label htmlFor="loop-iterate" className="text-xs">Iterate Over (Context Key)</Label>
                      <Input
                        id="loop-iterate"
                        value={config.iterate_over || ''}
                        onChange={(e) => handleUpdateActionConfig('iterate_over', e.target.value)}
                        placeholder="e.g., items, users"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label htmlFor="loop-item" className="text-xs">Item Variable</Label>
                      <Input
                        id="loop-item"
                        value={config.item_key || 'loop_item'}
                        onChange={(e) => handleUpdateActionConfig('item_key', e.target.value)}
                        placeholder="loop_item"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label htmlFor="loop-index" className="text-xs">Index Variable</Label>
                      <Input
                        id="loop-index"
                        value={config.index_key || 'loop_index'}
                        onChange={(e) => handleUpdateActionConfig('index_key', e.target.value)}
                        placeholder="loop_index"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label htmlFor="loop-body" className="text-xs">Loop Body Node</Label>
                      {renderNodeIdSelect('loop-body', config.loop_node, (v) => handleUpdateActionConfig('loop_node', v), 'Select node to execute per iteration...')}
                    </div>
                    <div>
                      <Label htmlFor="loop-done" className="text-xs">Done Node</Label>
                      {renderNodeIdSelect('loop-done', config.done_node, (v) => handleUpdateActionConfig('done_node', v), 'Select node to go to when done...')}
                    </div>
                    <div>
                      <Label htmlFor="loop-max" className="text-xs">Max Iterations</Label>
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
                  <Label className="mb-2 block">Action Configuration</Label>
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

      <div className="border-t border-border p-3 bg-card flex items-center justify-between gap-2">
        <div className="flex-1">
          {selectedNode && (
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive hover:text-destructive hover:bg-destructive/10"
              onClick={() => setShowDeleteConfirm(true)}
            >
              <Trash2 className="w-4 h-4 mr-1" />
              Delete Node
            </Button>
          )}
        </div>
        <Button variant="ghost" size="icon" className="h-8 w-8 hover:bg-accent" onClick={onToggle}>
          <PanelRightClose className="w-4 h-4 text-muted-foreground" />
        </Button>
      </div>

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Node</AlertDialogTitle>
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
