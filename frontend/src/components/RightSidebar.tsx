import { useState } from 'react';
import { PanelRightClose, Settings, Edit } from 'lucide-react';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Label } from './ui/label';
import { useFlowContext } from '../contexts/FlowContext';
import { NodeSelectionModal } from './modals/NodeSelectionModal';
import { ScheduleIntervalType, DocEventType } from '../types/flow.types';

interface RightSidebarProps {
  onToggle: () => void;
}

export function RightSidebar({ onToggle }: RightSidebarProps) {
  const { activeFlow, selectedNodeId, updateNode } = useFlowContext();
  const selectedNode = activeFlow?.nodes.find((n) => n.id === selectedNodeId);
  const [width, setWidth] = useState(380);
  const [isResizing, setIsResizing] = useState(false);
  const [isChangingTrigger, setIsChangingTrigger] = useState(false);

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (isResizing) {
      const newWidth = window.innerWidth - e.clientX;
      setWidth(Math.min(Math.max(320, newWidth), 600));
    }
  };

  const handleMouseUp = () => {
    setIsResizing(false);
  };

  useState(() => {
    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  });

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
            <Input
              id="doctype"
              value={config.doctype || ''}
              onChange={(e) => handleUpdateTriggerConfig('doctype', e.target.value)}
              placeholder="e.g., User, Order, Invoice"
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

            {selectedNode.data.nodeType === 'action' && selectedNode.data.actionConfig && (
              <div>
                <Label className="mb-2 block">Action Configuration</Label>
                <div className="p-3 rounded-md bg-muted/30 border border-border">
                  <code className="text-xs text-muted-foreground font-mono block overflow-x-auto">
                    {JSON.stringify(selectedNode.data.actionConfig, null, 2)}
                  </code>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <div className="border-t border-border p-3 bg-card">
        <Button variant="ghost" size="icon" className="h-8 w-8 hover:bg-accent" onClick={onToggle}>
          <PanelRightClose className="w-4 h-4 text-muted-foreground" />
        </Button>
      </div>

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
