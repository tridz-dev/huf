import { toast } from 'sonner';
import { useState, useEffect } from 'react';
import { PanelRightClose, Settings, Edit, Trash2 } from 'lucide-react';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Label } from './ui/label';
import { Combobox } from './ui/combobox';
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
import { getAgents, getDocTypes } from '../services/agentApi';
import { getToolFunctions, getToolFunction } from '../services/toolApi';
import { VariablePicker } from './ui/VariablePicker';

interface RightSidebarProps {
  onToggle: () => void;
}

export function RightSidebar({ onToggle }: RightSidebarProps) {
  const { activeFlow, selectedNodeId, selectedEdgeId, updateNode, deleteNode, updateEdges } = useFlowContext();
  const selectedNode = activeFlow?.nodes.find((n) => n.id === selectedNodeId);
  const selectedEdge = activeFlow?.edges.find((e) => e.id === selectedEdgeId);
  const [width, setWidth] = useState(380);
  const [isResizing, setIsResizing] = useState(false);
  const [isChangingTrigger, setIsChangingTrigger] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [agents, setAgents] = useState<Array<{ value: string; label: string }>>([]);
  const [tools, setTools] = useState<Array<{ value: string; label: string }>>([]);
  const [docTypes, setDocTypes] = useState<Array<{ value: string; label: string }>>([]);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [loadingTools, setLoadingTools] = useState(false);
  const [loadingDocTypes, setLoadingDocTypes] = useState(false);
  const [selectedToolDetails, setSelectedToolDetails] = useState<any | null>(null);
  const [loadingToolDetails, setLoadingToolDetails] = useState(false);

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

  // Load agents when agent-run node selected
  useEffect(() => {
    if (!selectedNode?.data.actionConfig || (selectedNode.data.actionConfig as any).type !== 'agent-run') return;
    setLoadingAgents(true);
    getAgents()
      .then((result) => {
        const items = Array.isArray(result) ? result : result.items;
        setAgents(
          (items || []).map((a: { name: string; agent_name?: string }) => ({
            value: a.name,
            label: a.agent_name || a.name,
          }))
        );
      })
      .catch(() => setAgents([]))
      .finally(() => setLoadingAgents(false));
  }, [selectedNode?.id, selectedNode?.data.actionConfig]);

  // Load tools when tool-call node selected
  useEffect(() => {
    if (!selectedNode?.data.actionConfig || (selectedNode.data.actionConfig as any).type !== 'tool-call') return;
    setLoadingTools(true);
    getToolFunctions()
      .then((list) => {
        setTools(
          (list || []).map((t: { name: string; tool_name?: string }) => ({
            value: t.tool_name || t.name,
            label: t.tool_name || t.name,
          }))
        );
      })
      .catch(() => setTools([]))
      .finally(() => setLoadingTools(false));
  }, [selectedNode?.id, selectedNode?.data.actionConfig]);

  // Load specific tool details when a tool is selected
  useEffect(() => {
    if (!selectedNode?.data.actionConfig || (selectedNode.data.actionConfig as any).type !== 'tool-call') {
      setSelectedToolDetails(null);
      return;
    }

    const toolName = (selectedNode.data.actionConfig as any).tool_name;
    if (!toolName) {
      setSelectedToolDetails(null);
      return;
    }

    setLoadingToolDetails(true);
    getToolFunction(toolName)
      .then((details) => {
        setSelectedToolDetails(details);
      })
      .catch(() => setSelectedToolDetails(null))
      .finally(() => setLoadingToolDetails(false));
  }, [selectedNode?.id, (selectedNode?.data.actionConfig as any)?.tool_name]);

  // Load DocTypes when doc-event trigger selected
  useEffect(() => {
    if (
      !selectedNode?.data.triggerConfig ||
      (selectedNode.data.triggerConfig as any).type !== 'doc-event'
    )
      return;
    setLoadingDocTypes(true);
    getDocTypes()
      .then((list) => {
        setDocTypes(
          (list || []).map((dt: { name: string }) => ({ value: dt.name, label: dt.name }))
        );
      })
      .catch(() => setDocTypes([]))
      .finally(() => setLoadingDocTypes(false));
  }, [selectedNode?.id, selectedNode?.data.triggerConfig]);

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

  const handleUpdateTriggerConfig = (field: string, value: any) => {
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
              value={config.auth || ''}
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
      return (
        <>
          <div>
            <Label htmlFor="interval-type">Schedule Type</Label>
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
            <div>
              <Label htmlFor="interval">Interval</Label>
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
            <div>
              <Label htmlFor="cron">Cron Expression</Label>
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
            <Label htmlFor="doctype">Document Type</Label>
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
            <Label htmlFor="event">Event Type</Label>
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

  return (
    <div
      className="relative h-screen bg-card border-l border-border flex flex-col"
      style={{ width: `${width}px` }}
    >
      <div
        className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/50 transition-colors"
        onMouseDown={handleMouseDown}
      />

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
                  value={selectedEdge.data?.type || 'always'}
                  onValueChange={(value) => {
                    if (!activeFlow) return;
                    updateEdges(
                      activeFlow.edges.map((edge) =>
                        edge.id === selectedEdge.id ? { ...edge, data: { ...edge.data, type: value } } : edge
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

              {selectedEdge.data?.type === 'expression' && (
                <div>
                  <Label htmlFor="edge-expr" className="text-xs">Condition Expression</Label>
                  <Input
                    id="edge-expr"
                    value={selectedEdge.data?.expression || ''}
                    onChange={(e) => {
                      if (!activeFlow) return;
                      updateEdges(
                        activeFlow.edges.map((edge) =>
                          edge.id === selectedEdge.id ? { ...edge, data: { ...edge.data, expression: e.target.value } } : edge
                        )
                      );
                    }}
                    placeholder="e.g., {{context.status}} == 'approved'"
                  />
                </div>
              )}
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
              const handleUpdateActionConfig = (field: string, value: any) => {
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

              if (config.type === 'agent-run') {
                return (
                  <div className="space-y-3">
                    <Label className="mb-2 block text-sm font-semibold">Agent Configuration</Label>
                    <div>
                      <Label htmlFor="agent-name" className="text-xs">Agent</Label>
                      <Combobox
                        options={agents}
                        value={(config as any).agent_name || ''}
                        onValueChange={(v) => handleUpdateActionConfig('agent_name', v)}
                        placeholder={loadingAgents ? 'Loading...' : 'Select agent...'}
                        disabled={loadingAgents}
                        searchPlaceholder="Search agents..."
                        emptyText="No agent found."
                      />
                    </div>
                    <div>
                      <div className="flex justify-between items-center mb-1">
                        <Label htmlFor="prompt-template" className="text-xs">Prompt Template</Label>
                        <VariablePicker onSelect={(v) => {
                          const current = (config as any).prompt_template || '';
                          handleUpdateActionConfig('prompt_template', current + (current.length && !current.endsWith(' ') ? ' ' : '') + v);
                        }} />
                      </div>
                      <textarea
                        id="prompt-template"
                        className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={(config as any).prompt_template || ''}
                        onChange={(e) => handleUpdateActionConfig('prompt_template', e.target.value)}
                        placeholder="Enter prompt template. Use {{context.key}} for variables."
                      />
                    </div>
                    <div>
                      <Label htmlFor="save-key" className="text-xs">Save Response To</Label>
                      <Input
                        id="save-key"
                        value={(config as any).save_response_to_context || ''}
                        onChange={(e) => handleUpdateActionConfig('save_response_to_context', e.target.value)}
                        placeholder="e.g., agent_response"
                      />
                    </div>
                  </div>
                );
              }

              if (config.type === 'tool-call') {
                return (
                  <div className="space-y-3">
                    <Label className="mb-2 block text-sm font-semibold">Tool Configuration</Label>
                    <div>
                      <Label htmlFor="tool-name" className="text-xs">Tool</Label>
                      <Combobox
                        options={tools}
                        value={(config as any).tool_name || ''}
                        onValueChange={(v) => handleUpdateActionConfig('tool_name', v)}
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
                      ) : selectedToolDetails.parameters && selectedToolDetails.parameters.length > 0 ? (
                        <div className="space-y-3 p-3 bg-muted/20 border rounded-md">
                          {selectedToolDetails.parameters.map((param: any) => {
                            const currentArgs = (config as any).args || {};
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
                                        const current = currentArgs[param.fieldname] || '';
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
                                  value={currentArgs[param.fieldname] || ''}
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
                        value={((config as any).output?.save_result_to_context) || ''}
                        onChange={(e) => handleUpdateActionConfig('output', { ...((config as any).output || {}), save_result_to_context: e.target.value })}
                        placeholder="e.g., tool_result"
                      />
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
                        options={agents}
                        value={(config as any).router_agent_name || ''}
                        onValueChange={(v) => handleUpdateActionConfig('router_agent_name', v)}
                        placeholder={loadingAgents ? 'Loading...' : 'Select routing agent...'}
                        disabled={loadingAgents}
                        searchPlaceholder="Search agents..."
                        emptyText="No agent found."
                      />
                    </div>
                    <div>
                      <Label htmlFor="conv-mode" className="text-xs">Conversation Mode</Label>
                      <Select
                        value={(config as any).conversation_mode || 'flow_shared'}
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
                  </div>
                );
              }

              if (config.type === 'human-in-loop') {
                return (
                  <div className="space-y-3">
                    <Label className="mb-2 block text-sm font-semibold">Human Approval Configuration</Label>
                    <div>
                      <Label htmlFor="approval-title" className="text-xs">Title</Label>
                      <Input
                        id="approval-title"
                        value={(config as any).title || ''}
                        onChange={(e) => handleUpdateActionConfig('title', e.target.value)}
                        placeholder="e.g., System Access Approval"
                      />
                    </div>
                    <div>
                      <Label htmlFor="approval-instructions" className="text-xs">Instructions</Label>
                      <textarea
                        id="approval-instructions"
                        className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={(config as any).instructions || ''}
                        onChange={(e) => handleUpdateActionConfig('instructions', e.target.value)}
                        placeholder="Detailed instructions for the approver"
                      />
                    </div>
                    <div>
                      <Label htmlFor="approver-role" className="text-xs">Approver Role (System Role)</Label>
                      <Input
                        id="approver-role"
                        value={(config as any).approver_role || ''}
                        onChange={(e) => handleUpdateActionConfig('approver_role', e.target.value)}
                        placeholder="e.g., System Manager"
                      />
                    </div>
                    <div>
                      <Label htmlFor="save-decision" className="text-xs">Store Decision in Context Key</Label>
                      <Input
                        id="save-decision"
                        value={(config as any).store_decision_in_context || ''}
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
                          const current = (config as any).expression || '';
                          handleUpdateActionConfig('expression', current + (current.length && !current.endsWith(' ') ? ' ' : '') + v);
                        }} />
                      </div>
                      <textarea
                        id="condition-expr"
                        className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={(config as any).expression || ''}
                        onChange={(e) => handleUpdateActionConfig('expression', e.target.value)}
                        placeholder='context["status"] == "approved"'
                      />
                    </div>
                    <div>
                      <Label htmlFor="true-node" className="text-xs">True Branch (Node ID)</Label>
                      <Input
                        id="true-node"
                        value={(config as any).true_node || ''}
                        onChange={(e) => handleUpdateActionConfig('true_node', e.target.value)}
                        placeholder="Node ID when True"
                      />
                    </div>
                    <div>
                      <Label htmlFor="false-node" className="text-xs">False Branch (Node ID)</Label>
                      <Input
                        id="false-node"
                        value={(config as any).false_node || ''}
                        onChange={(e) => handleUpdateActionConfig('false_node', e.target.value)}
                        placeholder="Node ID when False"
                      />
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
                          const current = (config as any).url || '';
                          handleUpdateActionConfig('url', current + (current.length && !current.endsWith(' ') ? ' ' : '') + v);
                        }} />
                      </div>
                      <Input
                        id="http-url"
                        value={(config as any).url || ''}
                        onChange={(e) => handleUpdateActionConfig('url', e.target.value)}
                        placeholder="https://api.example.com/endpoint"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label htmlFor="http-method" className="text-xs">Method</Label>
                      <Select
                        value={(config as any).method || 'GET'}
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
                        value={typeof (config as any).headers === 'object'
                          ? JSON.stringify((config as any).headers, null, 2)
                          : (config as any).headers || ''}
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
                      <Label htmlFor="http-body" className="text-xs">Body</Label>
                      <textarea
                        id="http-body"
                        className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-xs font-mono ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={typeof (config as any).body === 'object'
                          ? JSON.stringify((config as any).body, null, 2)
                          : (config as any).body || ''}
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
                      <Label htmlFor="http-timeout" className="text-xs">Timeout (seconds)</Label>
                      <Input
                        id="http-timeout"
                        type="number"
                        min={1}
                        max={300}
                        value={(config as any).timeout || 30}
                        onChange={(e) => handleUpdateActionConfig('timeout', parseInt(e.target.value))}
                      />
                    </div>
                    <div>
                      <Label htmlFor="http-save" className="text-xs">Save Result To Context</Label>
                      <Input
                        id="http-save"
                        value={(config as any).save_result_to_context || ''}
                        onChange={(e) => handleUpdateActionConfig('save_result_to_context', e.target.value)}
                        placeholder="e.g., api_response"
                      />
                    </div>
                  </div>
                );
              }

              if (config.type === 'transform') {
                const transformations = (config as any).transformations || [];
                return (
                  <div className="space-y-3">
                    <Label className="mb-2 block text-sm font-semibold">Transform Data Configuration</Label>
                    <div className="text-xs text-muted-foreground p-2 bg-muted/30 rounded-md mb-2">
                      Map, copy, or template data between context variables.
                    </div>
                    {transformations.map((t: any, i: number) => (
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
                          <Label className="text-[10px]">Source Field</Label>
                          <Input
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
                          <Label className="text-[10px]">Target Field</Label>
                          <Input
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
                          <Label className="text-[10px]">Operation</Label>
                          <Select
                            value={t.operation || 'copy'}
                            onValueChange={(v) => {
                              const updated = [...transformations];
                              updated[i] = { ...t, operation: v };
                              handleUpdateActionConfig('transformations', updated);
                            }}
                          >
                            <SelectTrigger className="h-7 text-xs">
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
                        value={(config as any).iterate_over || ''}
                        onChange={(e) => handleUpdateActionConfig('iterate_over', e.target.value)}
                        placeholder="e.g., items, users"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label htmlFor="loop-item" className="text-xs">Item Variable</Label>
                      <Input
                        id="loop-item"
                        value={(config as any).item_key || 'loop_item'}
                        onChange={(e) => handleUpdateActionConfig('item_key', e.target.value)}
                        placeholder="loop_item"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label htmlFor="loop-index" className="text-xs">Index Variable</Label>
                      <Input
                        id="loop-index"
                        value={(config as any).index_key || 'loop_index'}
                        onChange={(e) => handleUpdateActionConfig('index_key', e.target.value)}
                        placeholder="loop_index"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div>
                      <Label htmlFor="loop-body" className="text-xs">Loop Body Node (Node ID)</Label>
                      <Input
                        id="loop-body"
                        value={(config as any).loop_node || ''}
                        onChange={(e) => handleUpdateActionConfig('loop_node', e.target.value)}
                        placeholder="Node to execute per iteration"
                      />
                    </div>
                    <div>
                      <Label htmlFor="loop-done" className="text-xs">Done Node (Node ID)</Label>
                      <Input
                        id="loop-done"
                        value={(config as any).done_node || ''}
                        onChange={(e) => handleUpdateActionConfig('done_node', e.target.value)}
                        placeholder="Node to go to when done"
                      />
                    </div>
                    <div>
                      <Label htmlFor="loop-max" className="text-xs">Max Iterations</Label>
                      <Input
                        id="loop-max"
                        type="number"
                        min={1}
                        max={10000}
                        value={(config as any).max_iterations || 100}
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
