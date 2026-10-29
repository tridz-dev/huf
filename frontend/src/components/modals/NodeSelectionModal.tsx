import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogDescription,
  DialogTitle,
} from '../ui/dialog';
import {
  DialogScrollBody,
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '../ui/dialog-scroll';
import { Tabs, TabsContent } from '../ui/tabs';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Search } from 'lucide-react';
import { triggerOptions } from '../../data/triggers';
import { ACTION_SECTIONS, actionOptions } from '../../data/actions';
import { paletteIcon } from '../nodes/nodeIcons';
import { TriggerConfig, ActionConfig } from '../../types/flow.types';
import type { ActionOption } from '../../types/modal.types';
import { generateWebhookSecret } from '../../lib/flow-graph/flowWebhookUi';
import { DEFAULT_PICKER, pickerToCron } from '../../lib/flow-graph/flowSchedule';
import { CODE_RUN_ACTION, DEFAULT_CODE_PROFILE, DEFAULT_CODE_TIMEOUT_S } from '../../lib/flow-graph/codeFlow';
import { useCodeFlowStatus } from '../../lib/flow-graph/useCodeFlowStatus';
import { useFlowPermissions } from '../../hooks/flow/useFlowPermissions';

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
  // The Execute code card only shows while the server allows code in Flows and this user may run it.
  const { status: codeStatus } = useCodeFlowStatus();
  const { canExecuteCode } = useFlowPermissions();
  const codeAvailable = Boolean(codeStatus?.available) && canExecuteCode;
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

  const query = searchQuery.trim().toLowerCase();
  const matches = (text: Array<string | undefined>) => !query || text.some((t) => t?.toLowerCase().includes(query));

  const filteredTriggers = triggerOptions.filter((trigger) => matches([trigger.name, trigger.description]));

  const filteredActions = actionOptions.filter(
    (action) =>
      (!actionCategory || action.category === actionCategory) &&
      (action.id !== CODE_RUN_ACTION || codeAvailable) &&
      matches([action.name, action.description, ...(action.keywords ?? [])])
  );

  const highlightTriggers = filteredTriggers.filter((t) => t.category === 'highlight');

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
      'code-run': { type: 'code-run', code: '', profile: codeStatus?.default_profile || DEFAULT_CODE_PROFILE, inputs: {}, timeout_s: DEFAULT_CODE_TIMEOUT_S },
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

  const renderTile = (option: { id: string; name: string; description?: string; icon?: string }, onClick: () => void, selectedTile = false) => {
    const Icon = paletteIcon(option.icon);
    return (
      <Button
        key={option.id}
        type="button"
        variant="ghost"
        data-testid={`flow-card-${option.id}`}
        className={`flex h-auto w-full min-w-0 items-center justify-start gap-3 rounded-lg border p-3 font-normal ${selectedTile
          ? 'border-signal bg-panel hover:bg-panel'
          : 'border-line hover:border-ink hover:bg-paper-deep'
          }`}
        onClick={onClick}
      >
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded bg-primary/10">
          <Icon className="h-4 w-4 text-primary" aria-hidden />
        </div>
        <div className="min-w-0 flex-1 text-left">
          <div className="truncate text-sm font-medium" title={option.name}>{option.name}</div>
          {option.description && (
            <div className="mt-0.5 truncate text-xs leading-snug text-steel" title={option.description} data-testid={`flow-card-desc-${option.id}`}>
              {option.description}
            </div>
          )}
        </div>
      </Button>
    );
  };

  const renderActionCategory = (title: string, category: ActionOption['category']) => {
    const actions = filteredActions.filter((a) => a.category === category);
    if (actions.length === 0) return null;

    return (
      <div className="mb-6" data-testid={`flow-palette-section-${category}`}>
        <h3 className="mb-3 text-sm font-medium text-steel">{title}</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {actions.map((action) => renderTile(action, () => handleSelectAction(action.id)))}
        </div>
      </div>
    );
  };

  const nothingFound = mainTab === 'triggers' ? highlightTriggers.length === 0 : filteredActions.length === 0;
  const emptyState = (
    <div className="flex flex-col items-center gap-2 py-12 text-center" data-testid="flow-palette-empty">
      <Search className="h-6 w-6 text-steel-soft" aria-hidden />
      <p className="text-sm font-medium">No {mainTab === 'triggers' ? 'triggers' : 'steps'} match "{searchQuery.trim()}"</p>
      <p className="text-sm text-steel">
        {mainTab === 'triggers' ? 'Try "web", "schedule" or "record".' : 'Try "email", "agent" or "if".'}
      </p>
      <Button variant="outline" size="sm" data-testid="flow-palette-clear-search" onClick={() => setSearchQuery('')}>
        Show all
      </Button>
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogScrollContent className="h-[min(680px,85dvh)] max-w-3xl" data-testid={mainTab === 'triggers' ? 'flow-trigger-modal' : 'flow-action-modal'}>
        <DialogScrollHeader>
          <DialogTitle>
            {mainTab === 'triggers' ? 'Choose what starts this flow' : 'Add a step'}
          </DialogTitle>
          <DialogDescription data-testid="flow-palette-intro">
            {mainTab === 'triggers'
              ? 'Pick what makes the flow start. You set it up in the side panel next.'
              : 'Each step does one job and passes its result to the next one. Pick a step to add it here.'}
          </DialogDescription>
        </DialogScrollHeader>

        <DialogScrollBody className="flex flex-col pb-4">
        <div className="relative mb-4 flex-shrink-0">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-steel-soft" />
          <Input
            placeholder={mainTab === 'triggers' ? 'Search triggers...' : 'Search steps...'}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        <Tabs value={mainTab} onValueChange={(v) => { setMainTab(v as MainTab); setSelectedItem(null); setTriggerConfig({ type: undefined }); }} className="flex-1 flex flex-col min-h-0">
          <TabsContent value="triggers" className="mt-4 flex-1 overflow-y-auto scrollbar-hidden">
            {nothingFound ? emptyState : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2" data-testid="flow-trigger-palette">
                {highlightTriggers.map((trigger) => renderTile(trigger, () => handleSelectTrigger(trigger.id), selectedItem === trigger.id))}
              </div>
            )}
            {selectedItem && !nothingFound && (
              <p className="mt-4 text-sm text-muted-foreground">
                Add the trigger, then finish setting it up in the sidebar.
              </p>
            )}
          </TabsContent>

          <TabsContent value="actions" className="mt-4 flex-1 overflow-y-auto scrollbar-hidden">
            {nothingFound ? emptyState : ACTION_SECTIONS.map((section) => renderActionCategory(section.title, section.category))}
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
