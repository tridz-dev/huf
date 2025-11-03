import { useState } from 'react';
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
import { Search, Webhook, Clock, Mail, MessageSquare, FileText, Calendar, Database, Sheet } from 'lucide-react';
import { triggerOptions } from '../../data/triggers';
import { TriggerConfig, ScheduleIntervalType, DocEventType } from '../../types/flow.types';
import { ModalTab } from '../../types/modal.types';

interface TriggerConfigModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (config: TriggerConfig) => void;
  initialConfig?: TriggerConfig;
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
  UserCheck: Clock
};

export function TriggerConfigModal({
  open,
  onClose,
  onSave,
  initialConfig
}: TriggerConfigModalProps) {
  const [activeTab, setActiveTab] = useState<ModalTab>('explore');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTrigger, setSelectedTrigger] = useState<string | null>(
    initialConfig?.type || null
  );
  const [config, setConfig] = useState<TriggerConfig>(
    initialConfig || { type: undefined }
  );

  const filteredTriggers = triggerOptions.filter(
    (trigger) =>
      trigger.tab === activeTab &&
      trigger.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const popularTriggers = filteredTriggers.filter((t) => t.category === 'popular');
  const highlightTriggers = filteredTriggers.filter((t) => t.category === 'highlight');

  const handleSelectTrigger = (triggerId: string) => {
    setSelectedTrigger(triggerId);
    if (triggerId === 'webhook') {
      setConfig({
        type: 'webhook',
        url: `https://api.example.com/webhook/${Math.random().toString(36).substring(7)}`,
        apiKey: Math.random().toString(36).substring(2, 15),
        method: 'POST'
      });
    } else if (triggerId === 'schedule') {
      setConfig({
        type: 'schedule',
        intervalType: 'hours',
        interval: 1
      });
    } else if (triggerId === 'doc-event') {
      setConfig({
        type: 'doc-event',
        doctype: '',
        event: 'save'
      });
    } else if (triggerId.includes('gmail') || triggerId.includes('slack')) {
      setConfig({
        type: 'app-trigger',
        integration: triggerId as any,
        event: 'new_message'
      });
    }
  };

  const handleSave = () => {
    onSave(config);
    onClose();
  };

  const renderConfigForm = () => {
    if (!selectedTrigger) return null;

    if (config.type === 'webhook') {
      return (
        <div className="space-y-4 mt-4">
          <div>
            <Label htmlFor="webhook-url">Webhook URL</Label>
            <Input
              id="webhook-url"
              value={config.url || ''}
              onChange={(e) => setConfig({ ...config, url: e.target.value })}
              placeholder="https://api.example.com/webhook"
            />
          </div>
          <div>
            <Label htmlFor="api-key">API Key</Label>
            <Input
              id="api-key"
              value={config.apiKey || ''}
              onChange={(e) => setConfig({ ...config, apiKey: e.target.value })}
              placeholder="Enter API key"
            />
          </div>
          <div>
            <Label htmlFor="method">HTTP Method</Label>
            <Select
              value={config.method}
              onValueChange={(value) =>
                setConfig({ ...config, method: value as any })
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
                setConfig({ ...config, intervalType: value as ScheduleIntervalType })
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
                  setConfig({ ...config, interval: parseInt(e.target.value) })
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
                  setConfig({ ...config, cronExpression: e.target.value })
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
              onChange={(e) => setConfig({ ...config, doctype: e.target.value })}
              placeholder="e.g., User, Order, Invoice"
            />
          </div>
          <div>
            <Label htmlFor="event">Event Type</Label>
            <Select
              value={config.event}
              onValueChange={(value) =>
                setConfig({ ...config, event: value as DocEventType })
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
              onChange={(e) => setConfig({ ...config, event: e.target.value })}
              placeholder="e.g., new_message, new_email"
            />
          </div>
        </div>
      );
    }

    return null;
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Select Trigger</DialogTitle>
        </DialogHeader>

        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search triggers..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as ModalTab)}>
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="explore">Explore</TabsTrigger>
            <TabsTrigger value="ai-agents">AI & Agents</TabsTrigger>
            <TabsTrigger value="apps">Apps</TabsTrigger>
            <TabsTrigger value="utility">Utility</TabsTrigger>
          </TabsList>

          <TabsContent value={activeTab} className="flex-1 overflow-y-auto mt-4">
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
                          selectedTrigger === trigger.id
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
                          selectedTrigger === trigger.id
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
          </TabsContent>
        </Tabs>

        {renderConfigForm()}

        <div className="flex justify-end gap-2 mt-4 pt-4 border-t">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!selectedTrigger}>
            Save Configuration
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
