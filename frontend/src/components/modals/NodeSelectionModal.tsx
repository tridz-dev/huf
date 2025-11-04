import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Button } from '../ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Badge } from '../ui/badge';
import {
  Search,
  Webhook,
  Clock,
  Mail,
  MessageSquare,
  FileText,
  Calendar,
  Database,
  Sheet,
  Repeat,
  GitBranch,
  RotateCw,
  Code,
  Bot
} from 'lucide-react';
import { triggerOptions } from '../../data/triggers';
import { actionOptions } from '../../data/actions';
import { TriggerConfig, ActionConfig, ScheduleIntervalType, DocEventType } from '../../types/flow.types';
import { Agent } from '../../types/agent.types';
import { mockApi } from '../../services/mockApi';

interface NodeSelectionModalProps {
  open: boolean;
  onClose: () => void;
  mode: 'trigger' | 'action';
  onSaveTrigger?: (config: TriggerConfig) => void;
  onSaveAction?: (actionType: string, config: ActionConfig) => void;
  initialTriggerConfig?: TriggerConfig;
}

const iconMap: Record<string, any> = {
  Webhook,
  Clock,
  Mail,
  MessageSquare,
  FileText,
  Calendar,
  Database,
  Sheet,
  Repeat,
  GitBranch,
  RotateCw,
  Code,
  UserCheck: Clock
};

type MainTab = 'triggers' | 'actions';
type TriggerSubTab = 'explore' | 'ai-agents' | 'apps' | 'utility';

export function NodeSelectionModal({
  open,
  onClose,
  mode,
  onSaveTrigger,
  onSaveAction,
  initialTriggerConfig
}: NodeSelectionModalProps) {
  const [mainTab, setMainTab] = useState<MainTab>(mode === 'trigger' ? 'triggers' : 'actions');
  const [triggerSubTab, setTriggerSubTab] = useState<TriggerSubTab>('explore');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedItem, setSelectedItem] = useState<string | null>(
    initialTriggerConfig?.type || null
  );
  const [triggerConfig, setTriggerConfig] = useState<TriggerConfig>(
    initialTriggerConfig || { type: undefined }
  );
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(false);

  useEffect(() => {
    if (open && triggerSubTab === 'ai-agents') {
      setLoadingAgents(true);
      mockApi.agents.list().then((data) => {
        setAgents(data);
        setLoadingAgents(false);
      }).catch(() => {
        setLoadingAgents(false);
      });
    }
  }, [open, triggerSubTab]);

  const filteredTriggers = triggerOptions.filter(
    (trigger) =>
      trigger.tab === triggerSubTab &&
      trigger.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredActions = actionOptions.filter((action) =>
    action.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const highlightTriggers = filteredTriggers.filter((t) => t.category === 'highlight');
  const popularTriggers = filteredTriggers.filter((t) => t.category === 'popular');

  const transformActions = filteredActions.filter((a) => a.category === 'transform');
  const controlActions = filteredActions.filter((a) => a.category === 'control');
  const utilityActions = filteredActions.filter((a) => a.category === 'utility');
  const integrationActions = filteredActions.filter((a) => a.category === 'integration');

  const handleSelectTrigger = (triggerId: string) => {
    setSelectedItem(triggerId);
    if (triggerId === 'webhook') {
      setTriggerConfig({
        type: 'webhook',
        url: `https://api.example.com/webhook/${Math.random().toString(36).substring(7)}`,
        apiKey: Math.random().toString(36).substring(2, 15),
        method: 'POST'
      });
    } else if (triggerId === 'schedule') {
      setTriggerConfig({
        type: 'schedule',
        intervalType: 'hours',
        interval: 1
      });
    } else if (triggerId === 'doc-event') {
      setTriggerConfig({
        type: 'doc-event',
        doctype: '',
        event: 'save'
      });
    } else if (triggerId.includes('gmail') || triggerId.includes('slack')) {
      setTriggerConfig({
        type: 'app-trigger',
        integration: triggerId as any,
        event: 'new_message'
      });
    }
  };

  const handleSelectAction = (actionId: string) => {
    let config: ActionConfig = { type: undefined };

    if (actionId === 'transform') {
      config = { type: 'transform', transformations: [] };
    } else if (actionId === 'router') {
      config = { type: 'router', branches: [] };
    } else if (actionId === 'loop') {
      config = { type: 'loop', maxIterations: 10 };
    } else if (actionId === 'human-in-loop') {
      config = { type: 'human-in-loop', approvers: [] };
    } else if (actionId === 'code') {
      config = { type: 'code', language: 'javascript', code: '' };
    } else if (actionId === 'email') {
      config = { type: 'utility-email', to: '', subject: '', body: '' };
    } else if (actionId === 'webhook') {
      config = { type: 'utility-webhook', url: '', method: 'POST' };
    } else if (actionId === 'file') {
      config = { type: 'utility-file', operation: 'read', path: '' };
    } else if (actionId === 'date') {
      config = { type: 'utility-date', operation: 'format', format: 'YYYY-MM-DD' };
    }

    onSaveAction?.(actionId, config);
    onClose();
  };

  const handleSaveTrigger = () => {
    onSaveTrigger?.(triggerConfig);
    onClose();
  };

  const renderTriggerForm = () => {
    if (!selectedItem || mainTab !== 'triggers') return null;
    const config = triggerConfig;

    if (config.type === 'webhook') {
      return (
        <div className="space-y-4 mt-4">
          <div>
            <Label htmlFor="webhook-url">Webhook URL</Label>
            <Input
              id="webhook-url"
              value={config.url || ''}
              onChange={(e) => setTriggerConfig({ ...config, url: e.target.value })}
              placeholder="https://api.example.com/webhook"
            />
          </div>
          <div>
            <Label htmlFor="api-key">API Key</Label>
            <Input
              id="api-key"
              value={config.apiKey || ''}
              onChange={(e) => setTriggerConfig({ ...config, apiKey: e.target.value })}
              placeholder="Enter API key"
            />
          </div>
          <div>
            <Label htmlFor="method">HTTP Method</Label>
            <Select
              value={config.method}
              onValueChange={(value) =>
                setTriggerConfig({ ...config, method: value as any })
              }
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
        <div className="space-y-4 mt-4">
          <div>
            <Label htmlFor="interval-type">Schedule Type</Label>
            <Select
              value={config.intervalType}
              onValueChange={(value) =>
                setTriggerConfig({ ...config, intervalType: value as ScheduleIntervalType })
              }
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
                onChange={(e) =>
                  setTriggerConfig({ ...config, interval: parseInt(e.target.value) })
                }
              />
            </div>
          )}
          {config.intervalType === 'custom' && (
            <div>
              <Label htmlFor="cron">Cron Expression</Label>
              <Input
                id="cron"
                value={config.cronExpression || ''}
                onChange={(e) =>
                  setTriggerConfig({ ...config, cronExpression: e.target.value })
                }
                placeholder="0 */6 * * *"
              />
            </div>
          )}
        </div>
      );
    }

    if (config.type === 'doc-event') {
      return (
        <div className="space-y-4 mt-4">
          <div>
            <Label htmlFor="doctype">Document Type</Label>
            <Input
              id="doctype"
              value={config.doctype || ''}
              onChange={(e) => setTriggerConfig({ ...config, doctype: e.target.value })}
              placeholder="e.g., User, Order, Invoice"
            />
          </div>
          <div>
            <Label htmlFor="event">Event Type</Label>
            <Select
              value={config.event}
              onValueChange={(value) =>
                setTriggerConfig({ ...config, event: value as DocEventType })
              }
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
        </div>
      );
    }

    if (config.type === 'app-trigger') {
      return (
        <div className="space-y-4 mt-4">
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
              value={config.event || 'new_message'}
              onChange={(e) => setTriggerConfig({ ...config, event: e.target.value })}
              placeholder="e.g., new_message, new_email"
            />
          </div>
        </div>
      );
    }

    return null;
  };

  const renderActionCategory = (title: string, actions: typeof actionOptions) => {
    if (actions.length === 0) return null;

    return (
      <div className="mb-6">
        <h3 className="text-sm font-medium mb-3 text-muted-foreground">{title}</h3>
        <div className="grid grid-cols-2 gap-3">
          {actions.map((action) => {
            const Icon = iconMap[action.icon || 'FileText'];
            return (
              <button
                key={action.id}
                className="flex items-center gap-3 p-3 rounded-lg border border-border hover:border-primary/50 hover:bg-accent transition-all"
                onClick={() => handleSelectAction(action.id)}
              >
                <div className="w-8 h-8 rounded bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <Icon className="w-4 h-4 text-primary" />
                </div>
                <div className="text-left flex-1 min-w-0">
                  <div className="text-sm font-medium">{action.name}</div>
                  {action.description && (
                    <div className="text-xs text-muted-foreground truncate">
                      {action.description}
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>
            {mainTab === 'triggers' ? 'Select Trigger' : 'Add Action'}
          </DialogTitle>
        </DialogHeader>

        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder={`Search ${mainTab}...`}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        <Tabs value={mainTab} onValueChange={(v) => setMainTab(v as MainTab)}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="triggers">Triggers</TabsTrigger>
            <TabsTrigger value="actions">Actions</TabsTrigger>
          </TabsList>

          <TabsContent value="triggers" className="flex-1 overflow-hidden flex flex-col mt-4">
            <Tabs value={triggerSubTab} onValueChange={(v) => setTriggerSubTab(v as TriggerSubTab)}>
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="explore">Explore</TabsTrigger>
                <TabsTrigger value="ai-agents">AI & Agents</TabsTrigger>
                <TabsTrigger value="apps">Apps</TabsTrigger>
                <TabsTrigger value="utility">Utility</TabsTrigger>
              </TabsList>

              <TabsContent value={triggerSubTab} className="flex-1 overflow-y-auto mt-4">
                {triggerSubTab === 'ai-agents' ? (
                  loadingAgents ? (
                    <div className="flex items-center justify-center py-12">
                      <div className="text-muted-foreground">Loading agents...</div>
                    </div>
                  ) : agents.length === 0 ? (
                    <div className="flex items-center justify-center py-12">
                      <div className="text-center text-muted-foreground">
                        <Bot className="w-12 h-12 mx-auto mb-2 opacity-50" />
                        <p>No agents available</p>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <h3 className="text-sm font-medium mb-3 text-muted-foreground">
                        Available Agents
                      </h3>
                      <div className="space-y-2">
                        {agents.filter((agent) =>
                          agent.agent_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          agent.instructions.toLowerCase().includes(searchQuery.toLowerCase())
                        ).map((agent) => (
                          <button
                            key={agent.name}
                            className={`flex items-center gap-3 p-3 rounded-lg border w-full transition-all ${
                              selectedItem === agent.name
                                ? 'border-primary bg-primary/5'
                                : 'border-border hover:border-primary/50 hover:bg-accent'
                            }`}
                            onClick={() => {
                              setSelectedItem(agent.name);
                              setTriggerConfig({
                                type: 'app-trigger',
                                integration: 'agent' as any,
                                event: 'run_agent',
                                config: { agentId: agent.name, agentName: agent.agent_name }
                              });
                            }}
                          >
                            <div className="w-8 h-8 rounded bg-primary/10 flex items-center justify-center flex-shrink-0">
                              <Bot className="w-4 h-4 text-primary" />
                            </div>
                            <div className="text-left flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <div className="text-sm font-medium">{agent.agent_name}</div>
                                {agent.status && (
                                  <Badge variant={agent.status === 'Active' ? 'default' : 'secondary'} className="text-xs">
                                    {agent.status}
                                  </Badge>
                                )}
                              </div>
                              <div className="text-xs text-muted-foreground line-clamp-1">
                                {agent.instructions}
                              </div>
                              <div className="text-xs text-muted-foreground mt-1">
                                {agent.model} • {agent.category || 'General'}
                              </div>
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )
                ) : (
                  <>
                    {highlightTriggers.length > 0 && (
                      <div className="mb-6">
                        <h3 className="text-sm font-medium mb-3 text-muted-foreground">
                          Highlights
                        </h3>
                        <div className="grid grid-cols-2 gap-3">
                          {highlightTriggers.map((trigger) => {
                            const Icon = iconMap[trigger.icon || 'Webhook'];
                            return (
                              <button
                                key={trigger.id}
                                className={`flex items-center gap-3 p-3 rounded-lg border transition-all ${
                                  selectedItem === trigger.id
                                    ? 'border-primary bg-primary/5'
                                    : 'border-border hover:border-primary/50 hover:bg-accent'
                                }`}
                                onClick={() => handleSelectTrigger(trigger.id)}
                              >
                                <div className="w-8 h-8 rounded bg-primary/10 flex items-center justify-center flex-shrink-0">
                                  <Icon className="w-4 h-4 text-primary" />
                                </div>
                                <div className="text-left flex-1 min-w-0">
                                  <div className="text-sm font-medium">{trigger.name}</div>
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {popularTriggers.length > 0 && (
                      <div>
                        <h3 className="text-sm font-medium mb-3 text-muted-foreground">
                          Popular
                        </h3>
                        <div className="space-y-2">
                          {popularTriggers.map((trigger) => {
                            const Icon = iconMap[trigger.icon || 'Webhook'];
                            return (
                              <button
                                key={trigger.id}
                                className={`flex items-center gap-3 p-3 rounded-lg border w-full transition-all ${
                                  selectedItem === trigger.id
                                    ? 'border-primary bg-primary/5'
                                    : 'border-border hover:border-primary/50 hover:bg-accent'
                                }`}
                                onClick={() => handleSelectTrigger(trigger.id)}
                              >
                                <div className="w-8 h-8 rounded bg-primary/10 flex items-center justify-center flex-shrink-0">
                                  <Icon className="w-4 h-4 text-primary" />
                                </div>
                                <div className="text-left flex-1 min-w-0">
                                  <div className="text-sm font-medium">{trigger.name}</div>
                                  {trigger.description && (
                                    <div className="text-xs text-muted-foreground">
                                      {trigger.description}
                                    </div>
                                  )}
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </TabsContent>
            </Tabs>

            {renderTriggerForm()}
          </TabsContent>

          <TabsContent value="actions" className="flex-1 overflow-y-auto mt-4">
            {renderActionCategory('Transform', transformActions)}
            {renderActionCategory('Control Flow', controlActions)}
            {renderActionCategory('Utilities', utilityActions)}
            {renderActionCategory('Integrations', integrationActions)}
          </TabsContent>
        </Tabs>

        <div className="flex justify-end gap-2 mt-4 pt-4 border-t">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          {mainTab === 'triggers' && (
            <Button onClick={handleSaveTrigger} disabled={!selectedItem}>
              Save Configuration
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
