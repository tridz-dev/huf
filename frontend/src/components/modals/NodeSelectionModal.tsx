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
  Bot,
  UserCheck,
  Wrench
} from 'lucide-react';
import { triggerOptions } from '../../data/triggers';
import { actionOptions } from '../../data/actions';
import { TriggerConfig, ActionConfig, ScheduleIntervalType, DocEventType } from '../../types/flow.types';
import { Agent } from '../../types/agent.types';
import { getAgents, getDocTypes } from '../../services/agentApi';
import { AgentDoc } from '../../types/agent.types';
import { Combobox } from '../ui/combobox';
import { toast } from 'sonner';

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
  UserCheck,
  Bot,
  Wrench
};

type MainTab = 'triggers' | 'actions';
type TriggerSubTab = 'explore' | 'ai-agents';

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
  const [docTypes, setDocTypes] = useState<Array<{ name: string }>>([]);
  const [loadingDocTypes, setLoadingDocTypes] = useState(false);

  useEffect(() => {
    if (open && docTypes.length === 0 && !loadingDocTypes) {
      setLoadingDocTypes(true);
      getDocTypes()
        .then((data) => {
          setDocTypes(data);
          setLoadingDocTypes(false);
        })
        .catch((error) => {
          console.error('Error loading DocTypes:', error);
          setLoadingDocTypes(false);
        });
    }
  }, [open, docTypes.length, loadingDocTypes]);

  useEffect(() => {
    if (open && triggerSubTab === 'ai-agents') {
      setLoadingAgents(true);
      getAgents().then((result) => {
        const agentDocs = Array.isArray(result) ? result : result.items;
        // Map AgentDoc[] to Agent[] format expected by the component
        const mappedAgents: Agent[] = agentDocs.map((doc: AgentDoc) => ({
          name: doc.name,
          agent_name: doc.agent_name || doc.name,
          provider: '',
          model: doc.model || '',
          instructions: '',
          temperature: 1,
          top_p: 1,
          disabled: doc.disabled === 1,
          allow_chat: true,
          persist_conversation: true,
          triggers: [],
          tags: [],
          category: undefined,
          visibility: 'Global',
          environment: 'Prod',
          status: (doc.disabled === 1 ? 'Disabled' : 'Active') as Agent['status'],
          tools: [],
          stats: { conversations: 0, lastRunAt: '', successRate: 0, avgCost: 0, avgLatencyMs: 0, token24h: { input: 0, output: 0, total: 0 } },
          created_at: '',
          updated_at: '',
        }));
        setAgents(mappedAgents);
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

  const agentActions = filteredActions.filter((a) => a.category === 'agent');
  const toolActions = filteredActions.filter((a) => a.category === 'tool');
  const transformActions = filteredActions.filter((a) => a.category === 'transform');
  const controlActions = filteredActions.filter((a) => a.category === 'control');
  const utilityActions = filteredActions.filter((a) => a.category === 'utility');
  const integrationActions = filteredActions.filter((a) => a.category === 'integration');

  const handleSelectTrigger = (triggerId: string) => {
    setSelectedItem(triggerId);
    if (triggerId === 'webhook') {
      setTriggerConfig({
        type: 'webhook',
        url: `${window.location.origin}/api/method/huf.ai.flow_api.flow_webhook`,
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
    } else {
      // Clear any previous config form for triggers with no sub-settings
      setTriggerConfig({ type: undefined });
    }
  };

  const handleSelectAction = (actionId: string) => {
    let config: ActionConfig = { type: undefined };

    if (actionId === 'agent-run') {
      config = { type: 'agent-run', agent_name: '', prompt_template: '', save_response_to_context: '' };
    } else if (actionId === 'tool-call') {
      config = { type: 'tool-call', tool_name: '', args: {}, output: { save_result_to_context: '' } };
    } else if (actionId === 'condition') {
      config = { type: 'condition', expression: '', true_node: '', false_node: '' };
    } else if (actionId === 'router') {
      config = { type: 'router', router_agent_name: '', conversation_mode: 'flow_shared' };
    } else if (actionId === 'loop') {
      config = { type: 'loop', iterate_over: '', item_key: 'loop_item', index_key: 'loop_index', max_iterations: 100 };
    } else if (actionId === 'human.approval') {
      config = { type: 'human.approval', title: 'Approval Required', instructions: '', approval_type: 'role', store_decision_in_context: 'approval' };
    } else if (actionId === 'http-request') {
      config = { type: 'http-request', url: '', method: 'GET', timeout: 30 };
    } else if (actionId === 'transform') {
      config = { type: 'transform', transformations: [] };
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
        <div className="space-y-4 mt-4 overflow-y-auto max-h-[300px] pr-2 border rounded-md p-3 bg-muted/20">
          <div>
            <Label htmlFor="webhook-url">Webhook URL</Label>
            <div className="flex gap-2">
              <Input
                id="webhook-url"
                value={config.url || ''}
                readOnly
                className="bg-muted text-xs font-mono"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  navigator.clipboard.writeText(config.url || '');
                  toast.success('Copied to clipboard');
                }}
              >
                Copy
              </Button>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1">This is your endpoint. Send data here to trigger this flow.</p>
          </div>
          <div>
            <Label htmlFor="method">HTTP Method</Label>
            <Select
              value={config.method || 'POST'}
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
          <div>
            <Label htmlFor="api-key">Security — API Key (Optional)</Label>
            <Input
              id="api-key"
              value={config.apiKey || ''}
              onChange={(e) => setTriggerConfig({ ...config, apiKey: e.target.value })}
              placeholder="Enter API key to require X-API-Key header"
            />
          </div>
          <div>
            <Label htmlFor="headers">Custom Headers (JSON string)</Label>
            <textarea
              id="headers"
              className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-xs font-mono ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-ring"
              value={JSON.stringify(config.headers || {}, null, 2)}
              onChange={(e) => {
                try {
                  const headers = JSON.parse(e.target.value);
                  setTriggerConfig({ ...config, headers });
                } catch {
                  // Wait for valid JSON
                }
              }}
              placeholder='{ "X-Custom": "Value" }'
            />
          </div>
          <div>
            <Label htmlFor="body-template">Expected Body Template (JSON for validation or documentation)</Label>
            <textarea
              id="body-template"
              className="flex min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2 text-xs font-mono ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-ring"
              value={config.body_template || ''}
              onChange={(e) => setTriggerConfig({ ...config, body_template: e.target.value })}
              placeholder='{ "order_id": "123", "amount": 100 }'
            />
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
      const comboboxOptions = docTypes.map((dt) => ({
        value: dt.name,
        label: dt.name,
      }));

      return (
        <div className="space-y-4 mt-4">
          <div>
            <Label htmlFor="doctype">Document Type</Label>
            <Combobox
              options={comboboxOptions}
              value={config.doctype || ''}
              onValueChange={(value) => setTriggerConfig({ ...config, doctype: value })}
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
            // Super safe check to prevent React Error 130 (object without $$typeof)
            const isValidComponent = Icon && (typeof Icon === 'function' || (typeof Icon === 'object' && '$$typeof' in Icon));

            return (
              <button
                key={action.id}
                className="flex items-center gap-3 p-3 rounded-lg border border-border hover:border-primary/50 hover:bg-accent transition-all"
                onClick={() => handleSelectAction(action.id)}
              >
                <div className="w-8 h-8 rounded bg-primary/10 flex items-center justify-center flex-shrink-0">
                  {isValidComponent ? <Icon className="w-4 h-4 text-primary" /> : <div className="w-4 h-4" />}
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
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle>
            {mainTab === 'triggers' ? 'Select Trigger' : 'Add Action'}
          </DialogTitle>
        </DialogHeader>

        <div className="relative mb-4 flex-shrink-0">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder={`Search ${mainTab}...`}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        <Tabs value={mainTab} onValueChange={(v) => { setMainTab(v as MainTab); setSelectedItem(null); setTriggerConfig({ type: undefined }); }} className="flex-1 flex flex-col min-h-0">
          {mode !== 'trigger' ? (
            <TabsList className="grid w-full grid-cols-2 flex-shrink-0">
              <TabsTrigger value="triggers">Triggers</TabsTrigger>
              <TabsTrigger value="actions">Actions</TabsTrigger>
            </TabsList>
          ) : (
            <TabsList className="grid w-full grid-cols-1 flex-shrink-0">
              <TabsTrigger value="triggers">Triggers</TabsTrigger>
            </TabsList>
          )}

          <TabsContent value="triggers" className="flex-1 flex flex-col min-h-0 mt-4">
            <Tabs value={triggerSubTab} onValueChange={(v) => { setTriggerSubTab(v as TriggerSubTab); setSelectedItem(null); setTriggerConfig({ type: undefined }); }} className="flex-1 flex flex-col min-h-0">
              <TabsList className="grid w-full grid-cols-2 flex-shrink-0">
                <TabsTrigger value="explore">Explore</TabsTrigger>
                <TabsTrigger value="ai-agents">AI & Agents</TabsTrigger>
              </TabsList>

              <div className="flex-1 overflow-y-auto mt-4 scrollbar-hidden">
                <TabsContent value={triggerSubTab} className="mt-0">
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
                              className={`flex items-center gap-3 p-3 rounded-lg border w-full transition-all ${selectedItem === agent.name
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
                                  className={`flex items-center gap-3 p-3 rounded-lg border transition-all ${selectedItem === trigger.id
                                    ? 'border-primary bg-primary/5'
                                    : 'border-border hover:border-primary/50 hover:bg-accent'
                                    }`}
                                  onClick={() => handleSelectTrigger(trigger.id)}
                                >
                                  <div className="w-8 h-8 rounded bg-primary/10 flex items-center justify-center flex-shrink-0">
                                    {Icon ? <Icon className="w-4 h-4 text-primary" /> : <div className="w-4 h-4" />}
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
                                  className={`flex items-center gap-3 p-3 rounded-lg border w-full transition-all ${selectedItem === trigger.id
                                    ? 'border-primary bg-primary/5'
                                    : 'border-border hover:border-primary/50 hover:bg-accent'
                                    }`}
                                  onClick={() => handleSelectTrigger(trigger.id)}
                                >
                                  <div className="w-8 h-8 rounded bg-primary/10 flex items-center justify-center flex-shrink-0">
                                    {Icon ? <Icon className="w-4 h-4 text-primary" /> : <div className="w-4 h-4" />}
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

                {renderTriggerForm()}
              </div>
            </Tabs>
          </TabsContent>

          <TabsContent value="actions" className="flex-1 overflow-y-auto mt-4 scrollbar-hidden">
            {renderActionCategory('AI & Agents', agentActions)}
            {renderActionCategory('Tools', toolActions)}
            {renderActionCategory('Control Flow', controlActions)}
            {renderActionCategory('Transform', transformActions)}
            {renderActionCategory('Utilities', utilityActions)}
            {renderActionCategory('Integrations', integrationActions)}
          </TabsContent>
        </Tabs>

        <div className="flex justify-end gap-2 mt-4 pt-4 border-t flex-shrink-0">
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
