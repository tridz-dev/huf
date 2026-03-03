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
import { getToolFunctions } from '../services/toolApi';

interface RightSidebarProps {
  onToggle: () => void;
}

export function RightSidebar({ onToggle }: RightSidebarProps) {
  const { activeFlow, selectedNodeId, updateNode, deleteNode } = useFlowContext();
  const selectedNode = activeFlow?.nodes.find((n) => n.id === selectedNodeId);
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
      return (
        <>
          <div>
            <Label htmlFor="webhook-url">Webhook URL</Label>
            <Input
              id="webhook-url"
              value={config.url || ''}
              onChange={(e) => handleUpdateTriggerConfig('url', e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="api-key">API Key</Label>
            <Input
              id="api-key"
              value={config.apiKey || ''}
              onChange={(e) => handleUpdateTriggerConfig('apiKey', e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="method">HTTP Method</Label>
            <Select
              value={config.method}
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
        </>
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
        {!selectedNode ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Settings className="w-12 h-12 text-muted-foreground mb-4" />
            <div className="text-sm text-muted-foreground">
              Select a node to view configuration
            </div>
          </div>
        ) : (
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
                      <Label htmlFor="prompt-template" className="text-xs">Prompt Template</Label>
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
                      <Label htmlFor="tool-args" className="text-xs">Arguments (JSON)</Label>
                      <textarea
                        id="tool-args"
                        className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={JSON.stringify((config as any).args || {}, null, 2)}
                        onChange={(e) => {
                          try {
                            const parsed = JSON.parse(e.target.value);
                            handleUpdateActionConfig('args', parsed);
                          } catch {
                            // ignore invalid JSON while typing
                          }
                        }}
                        placeholder='{"query": "{{context.input}}"}'
                      />
                    </div>
                    <div>
                      <Label htmlFor="save-result" className="text-xs">Save Result To</Label>
                      <Input
                        id="save-result"
                        value={(config as any).save_result_to_context || ''}
                        onChange={(e) => handleUpdateActionConfig('save_result_to_context', e.target.value)}
                        placeholder="e.g., tool_result"
                      />
                    </div>
                  </div>
                );
              }

              if (config.type === 'human-in-loop') {
                return (
                  <div className="space-y-3">
                    <Label className="mb-2 block text-sm font-semibold">Human Approval</Label>
                    <div>
                      <Label htmlFor="approval-message" className="text-xs">Instructions</Label>
                      <textarea
                        id="approval-message"
                        className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={(config as any).message || ''}
                        onChange={(e) => handleUpdateActionConfig('message', e.target.value)}
                        placeholder="Instructions for the approver"
                      />
                    </div>
                    <div>
                      <Label htmlFor="timeout" className="text-xs">Timeout (seconds)</Label>
                      <Input
                        id="timeout"
                        type="number"
                        min="0"
                        value={(config as any).timeout || 0}
                        onChange={(e) => handleUpdateActionConfig('timeout', parseInt(e.target.value))}
                        placeholder="0 = no timeout"
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
        )}
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
