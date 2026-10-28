import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
} from '../ui/dialog';
import {
  DialogScrollBody,
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '../ui/dialog-scroll';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
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
  CheckCircle2,
  SquareAsterisk,
  UserCheck,
  Wrench,
  Globe,
  Save,
  Trash2,
  FilePlus,
  type LucideIcon
} from 'lucide-react';
import { triggerOptions } from '../../data/triggers';
import { actionOptions } from '../../data/actions';
import { TriggerConfig, ActionConfig } from '../../types/flow.types';
import type { ActionOption } from '../../types/modal.types';
import { generateWebhookSecret } from '../../lib/flowWebhookUi';
import { DEFAULT_PICKER, pickerToCron } from '../../lib/flowSchedule';

interface NodeSelectionModalProps {
  open: boolean;
  onClose: () => void;
  mode: 'trigger' | 'action';
  onSaveTrigger?: (config: TriggerConfig) => void;
  onSaveAction?: (actionType: string, config: ActionConfig) => void;
  initialTriggerConfig?: TriggerConfig;
  /**
   * Restrict the actions tab to a single category (used by the node palette
   * rail). Leave undefined to show every category, as the "Add step" flow does.
   */
  actionCategory?: ActionOption['category'] | null;
}
const iconMap: Record<string, LucideIcon> = {
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
  Wrench,
  Globe,
  Save,
  Trash2,
  FilePlus,
  CheckCircle2,
  SquareAsterisk,
};

type MainTab = 'triggers' | 'actions';

export function NodeSelectionModal({
  open,
  onClose,
  mode,
  onSaveTrigger,
  onSaveAction,
  initialTriggerConfig,
  actionCategory
}: NodeSelectionModalProps) {
  const [mainTab, setMainTab] = useState<MainTab>(mode === 'trigger' ? 'triggers' : 'actions');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedItem, setSelectedItem] = useState<string | null>(
    initialTriggerConfig?.type || null
  );
  const [triggerConfig, setTriggerConfig] = useState<TriggerConfig>(
    initialTriggerConfig || { type: undefined }
  );
  // NodeSelectionModal is always mounted (FlowCanvas renders it with `open=`,
  // not conditionally), so the useState initialisers above run exactly once —
  // on first mount — and never again. Without this effect, `mainTab` keeps
  // whatever value the FIRST open set: configure the entry node's trigger, then
  // click "+" on a later node, and the modal opens in action mode while still
  // showing the Triggers tab and trigger cards. Selecting one there routes to
  // the trigger-save handler with no target node, creating an orphan trigger.
  // Re-sync every time the modal opens or its mode changes.
  useEffect(() => {
    if (!open) return;
    setMainTab(mode === 'trigger' ? 'triggers' : 'actions');
    setSearchQuery('');
    setSelectedItem(initialTriggerConfig?.type || null);
    setTriggerConfig(initialTriggerConfig || { type: undefined });
  }, [open, mode, initialTriggerConfig]);

  // The modal stays mounted between openings, so its tab has to follow the
  // `mode` prop each time it is (re)opened.
  useEffect(() => {
    if (open) {
      setMainTab(mode === 'trigger' ? 'triggers' : 'actions');
      setSearchQuery('');
    }
  }, [open, mode]);

  const filteredTriggers = triggerOptions.filter(
    (trigger) =>
      trigger.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredActions = actionOptions.filter(
    (action) =>
      (!actionCategory || action.category === actionCategory) &&
      action.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const highlightTriggers = filteredTriggers.filter((t) => t.category === 'highlight');
  
  const agentActions = filteredActions.filter((a) => a.category === 'agent');
  const toolActions = filteredActions.filter((a) => a.category === 'tool');
  const transformActions = filteredActions.filter((a) => a.category === 'transform');
  const controlActions = filteredActions.filter((a) => a.category === 'control');
  const utilityActions = filteredActions.filter((a) => a.category === 'utility');
  const integrationActions = filteredActions.filter((a) => a.category === 'integration');

  const handleSelectTrigger = (triggerId: string) => {
    setSelectedItem(triggerId);
    if (triggerId === 'webhook') {
      // The secret is generated up front so the webhook is never open; it stays visible and regenerable in the sidebar.
      setTriggerConfig({ type: 'webhook', method: 'POST', secret: generateWebhookSecret() } as TriggerConfig);
    } else if (triggerId === 'schedule') {
      // Start from the picker's default (every day at 09:00) so what the form shows is what gets saved.
      setTriggerConfig({ type: 'schedule', cron: pickerToCron(DEFAULT_PICKER) } as TriggerConfig);
    } else if (triggerId === 'doc-event') {
      setTriggerConfig({ type: 'doc-event' });
    } else {
      setTriggerConfig({ type: undefined });
    }
  };

  const handleSelectAction = (actionId: string) => {
    const tool = (tool_id: string, input: Record<string, unknown> = {}) => ({ type: 'tool-call', tool_id, input });
    const configs: Record<string, Record<string, unknown>> = {
      'agent-run': { type: 'agent-run', agent: '', prompt: '' },
      'tool-call': tool(''),
      condition: { type: 'condition', expression: '' },
      router: { type: 'router', prompt: '' },
      loop: { type: 'foreach', items: { $from: '' }, max_iterations: 100, on_item_error: 'fail', collect: { $from: '' } },
      'human.approval': { type: 'human.approval', message: '' },
      end: { type: 'end' },
      'http-request': tool('http_request', { url: '', method: 'GET' }),
      transform: { type: 'transform', op: 'lower', input: {} },
      'state-get': { type: 'state-get', key: '' },
      'state-set': { type: 'state-set', key: '', value: '' },
      'state-delete': { type: 'state-delete', key: '' },
      'doc-create': { type: 'doc-create', doctype: '', fields: {} },
      email: tool('gmail_send_email'),
      slack: tool('slack_send_message'),
      sheets: tool('gsheets_read'),
      file: tool('gdrive_list_files'),
    };
    const config = (configs[actionId] ?? { type: undefined }) as unknown as ActionConfig;

    onSaveAction?.(actionId, config);
    onClose();
  };

  const handleSaveTrigger = () => {
    onSaveTrigger?.(triggerConfig);
    onClose();
  };

  const renderActionCategory = (title: string, actions: typeof actionOptions) => {
    if (actions.length === 0) return null;

    return (
      <div className="mb-6">
        <h3 className="text-sm font-medium mb-3 text-steel">{title}</h3>
        <div className="grid grid-cols-2 gap-3">
          {actions.map((action) => {
            const Icon = iconMap[action.icon || 'FileText'];
            // Super safe check to prevent React Error 130 (object without $$typeof)
            const isValidComponent = Icon && (typeof Icon === 'function' || (typeof Icon === 'object' && '$$typeof' in Icon));

            return (
              <Button
                key={action.id}
                type="button"
                variant="ghost"
                data-testid={`flow-card-${action.id}`}
                className="flex h-auto w-full items-center justify-start gap-3 rounded border border-line p-3 font-normal hover:border-ink hover:bg-paper-deep"
                onClick={() => handleSelectAction(action.id)}
              >
                <div className="w-8 h-8 rounded bg-primary/10 flex items-center justify-center flex-shrink-0">
                  {isValidComponent ? <Icon className="w-4 h-4 text-primary" /> : <div className="w-4 h-4" />}
                </div>
                <div className="text-left flex-1 min-w-0">
                  <div className="text-sm font-medium">{action.name}</div>
                  {action.description && (
                    <div className="text-xs text-steel-soft truncate">
                      {action.description}
                    </div>
                  )}
                </div>
              </Button>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogScrollContent className="max-w-3xl" data-testid={mainTab === 'triggers' ? 'flow-trigger-modal' : 'flow-action-modal'}>
        <DialogScrollHeader>
          <DialogTitle>
            {mainTab === 'triggers' ? 'Choose a trigger' : 'Add a step'}
          </DialogTitle>
        </DialogScrollHeader>

        <DialogScrollBody className="flex flex-col pb-4">
        <div className="relative mb-4 flex-shrink-0">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-steel-soft" />
          <Input
            placeholder={`Search ${mainTab}...`}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        <Tabs value={mainTab} onValueChange={(v) => { setMainTab(v as MainTab); setSelectedItem(null); setTriggerConfig({ type: undefined }); }} className="flex-1 flex flex-col min-h-0">
          {/* In action mode the modal must not offer a Triggers tab at all: a
              trigger belongs only to the entry node, and selecting one here
              routes to the trigger-save handler with no target node, silently
              creating a disconnected orphan trigger. `mode` already determines
              the content, so the tab bar is redundant as well as harmful. */}
          {mode !== 'trigger' ? null : (
            <TabsList layout="grid" cols={1} className="flex-shrink-0">
              <TabsTrigger value="triggers">Triggers</TabsTrigger>
            </TabsList>
          )}

          <TabsContent value="triggers" className="flex-1 overflow-y-auto mt-4 scrollbar-hidden">
            <div className="grid grid-cols-2 gap-3" data-testid="flow-trigger-palette">
              {highlightTriggers.map((trigger) => {
                const Icon = iconMap[trigger.icon || 'Webhook'];
                return (
                  <Button
                    key={trigger.id}
                    type="button"
                    variant="ghost"
                    data-testid={`flow-card-${trigger.id}`}
                    className={`flex h-auto items-center justify-start gap-3 rounded-lg border p-3 font-normal ${selectedItem === trigger.id
                      ? 'border-signal bg-panel hover:bg-panel'
                      : 'border-line hover:border-ink hover:bg-paper-deep'
                      }`}
                    onClick={() => handleSelectTrigger(trigger.id)}
                  >
                    <div className="w-8 h-8 rounded bg-primary/10 flex items-center justify-center flex-shrink-0">
                      {Icon ? <Icon className="w-4 h-4 text-primary" /> : <div className="w-4 h-4" />}
                    </div>
                    <div className="text-left flex-1 min-w-0">
                      <div className="text-sm font-medium">{trigger.name}</div>
                      {trigger.description && <div className="text-xs text-steel-soft">{trigger.description}</div>}
                    </div>
                  </Button>
                );
              })}
            </div>
            {selectedItem && (
              <p className="mt-4 text-sm text-muted-foreground">
                Add the trigger, then finish setting it up in the sidebar.
              </p>
            )}
          </TabsContent>

          <TabsContent value="actions" className="flex-1 overflow-y-auto mt-4 scrollbar-hidden">
            {renderActionCategory('AI & Agents', agentActions)}
            {renderActionCategory('Tools', toolActions)}
            {renderActionCategory('Control Flow', controlActions)}
            {renderActionCategory('Transform & State', transformActions)}
            {renderActionCategory('Utilities', utilityActions)}
            {renderActionCategory('Integrations', integrationActions)}
          </TabsContent>
        </Tabs>
        </DialogScrollBody>

        <DialogScrollFooter className="justify-end">
          <Button variant="outline" data-testid="flow-modal-cancel" onClick={onClose}>
            Cancel
          </Button>
          {mainTab === 'triggers' && (
            <Button data-testid="flow-modal-add-trigger" onClick={handleSaveTrigger} disabled={!selectedItem}>
              Add trigger
            </Button>
          )}
        </DialogScrollFooter>
      </DialogScrollContent>
    </Dialog>
  );
}
