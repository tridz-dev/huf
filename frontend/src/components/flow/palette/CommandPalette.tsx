import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CircleHelp, Copy, History, Keyboard, LayoutTemplate, Play, Redo2, Save, Settings, Undo2, Upload, ClipboardPaste, FileText } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandShortcut } from '@/components/ui/command';
import { useFlowContext } from '@/contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { useShortcutsHelp } from '@/components/shortcuts/ShortcutsHelpContext';
import { actionOptions } from '@/data/actions';
import { paletteIcon, cardIcon } from '@/components/nodes/nodeIcons';
import { CODE_RUN_ACTION } from '@/lib/flow-graph/codeFlow';
import { useCodeFlowStatus } from '@/lib/flow-graph/useCodeFlowStatus';
import { insertSpot } from '@/lib/flow-history/insertStep';
import { readClipboard } from '@/lib/flow-history/flowClipboard';
import { readRecentFlows } from '@/lib/flow-history/recentFlows';
import { stepKindLabel } from '../frame/StepHeader';
import { runFlowCommand } from '../shortcuts/flowCommands';
import { shortcutText } from '../shortcuts/shortcutHints';
import { useFlowStepActions } from '../shortcuts/useFlowStepActions';
import { StatusPill, flowStatusKind } from '@/components/common/StatusPill';
import { cn } from '@/lib/utils';
import { paletteFilter } from './paletteFilter';

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Steps currently selected on the canvas (ids). */
  getSelectedIds: () => string[];
  onOpenHelp: () => void;
}

/**
 * Cmd+K in the flow editor: add a step (behind the selected one, or at the end), jump to any step by its title, open another flow,
 * or run an editor action. Type to filter; Enter does the highlighted one; Esc closes. Everything is a plain button as well
 * (the header, the "..." menus), this is the keyboard way to all of it.
 */
export function FlowCommandPalette({ open, onOpenChange, getSelectedIds, onOpenHelp }: CommandPaletteProps) {
  const navigate = useNavigate();
  const { activeFlow, flows, activeFlowId, hasUnsavedChanges, undo, redo, canUndo, canRedo, undoLabel, redoLabel, tidyLayout, setSelectedNode } = useFlowContext();
  const { canManage, canExecuteCode } = useFlowPermissions();
  const { status: codeStatus } = useCodeFlowStatus();
  const { setOpen: openShortcuts } = useShortcutsHelp();
  const actions = useFlowStepActions();
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [recent, setRecent] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    setSearch('');
    setSelected(getSelectedIds());
    setRecent(readRecentFlows());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const nodes = activeFlow?.nodes ?? [];
  const afterId = selected.length === 1 ? selected[0] : null;
  const spot = useMemo(() => (activeFlow ? insertSpot({ nodes: activeFlow.nodes, edges: activeFlow.edges }, afterId) : null), [activeFlow, afterId]);
  const afterNode = spot ? nodes.find((n) => n.id === spot.sourceId) : undefined;
  const codeAvailable = Boolean(codeStatus?.available) && canExecuteCode;
  const addable = actionOptions.filter((a) => a.id !== CODE_RUN_ACTION || codeAvailable);
  const ordered = addable;
  const isLive = activeFlow?.status === 'active';
  const clip = open ? readClipboard() : null;
  const searching = search.trim().length > 0;

  const close = () => onOpenChange(false);
  const run = (fn: () => void) => () => {
    close();
    // Let the dialog hand focus back before the action opens something of its own.
    window.setTimeout(fn, 0);
  };

  const flowRows = (searching ? flows.filter((f) => f.id !== activeFlowId) : recent.map((id) => flows.find((f) => f.id === id)).filter((f): f is NonNullable<typeof f> => Boolean(f) && f?.id !== activeFlowId)).slice(0, searching ? 50 : 5);

  const row = 'gap-2.5 px-2 py-2 focus-visible:ring-2 focus-visible:ring-ring';
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="top-[18%] translate-y-0 gap-0 overflow-hidden p-0 sm:top-[18%] sm:max-w-xl sm:translate-y-0 motion-reduce:animate-none motion-reduce:transition-none motion-reduce:duration-0"
        data-testid="flow-palette"
        onCloseAutoFocus={(e) => e.preventDefault()}
      >
        <DialogTitle className="sr-only">Search steps, flows and actions</DialogTitle>
        <DialogDescription className="sr-only">Type to filter. Use the arrow keys to move and Enter to choose.</DialogDescription>
        <Command loop filter={paletteFilter} className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium">
          <CommandInput
            value={search}
            onValueChange={setSearch}
            placeholder="Search steps to add, steps in this flow, flows and actions"
            aria-label="Search steps, flows and actions"
            data-testid="flow-palette-input"
          />
          <CommandList className="max-h-[min(420px,60dvh)]" data-testid="flow-palette-list">
            <CommandEmpty data-testid="flow-palette-no-results">Nothing matches &ldquo;{search.trim()}&rdquo;. Try a step name such as &ldquo;email&rdquo;.</CommandEmpty>

            {canManage && spot && (
              <CommandGroup heading={afterNode ? `Add a step after “${afterNode.data.label}”` : 'Add a step at the end'} data-testid="flow-palette-add">
                {ordered.map((a) => {
                  const Icon = paletteIcon(a.icon);
                  return (
                    <CommandItem
                      key={a.id}
                      value={`add ${a.name}`}
                      keywords={[a.description ?? '', a.id, ...(a.keywords ?? [])]}
                      className={row}
                      data-testid={`flow-palette-add-${a.id}`}
                      onSelect={run(() => actions.addStep(a.id, a.name, afterId, codeStatus?.default_profile))}
                    >
                      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{a.name}</span>
                        {a.description && <span className="block truncate text-xs text-muted-foreground">{a.description}</span>}
                      </span>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            )}

            {nodes.length > 0 && (
              <CommandGroup heading="Go to a step" data-testid="flow-palette-goto">
                {nodes.map((n) => {
                  const Icon = cardIcon(n.data);
                  return (
                    <CommandItem
                      key={n.id}
                      value={`go to ${n.data.label} ${n.id}`}
                      keywords={[stepKindLabel(n), n.id]}
                      className={row}
                      data-testid={`flow-palette-goto-${n.id}`}
                      onSelect={run(() => setSelectedNode(n.id))}
                    >
                      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                      <span className="min-w-0 flex-1 truncate font-medium">{n.data.label}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">{stepKindLabel(n)}</span>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            )}

            <CommandGroup heading="Actions" data-testid="flow-palette-actions">
              {canManage && (
                <PaletteAction id="save" icon={Save} label="Save" shortcut="flow-save" hint={hasUnsavedChanges ? undefined : 'Nothing new to save'} onSelect={run(() => runFlowCommand('save'))} className={row} />
              )}
              {canManage && !isLive && <PaletteAction id="publish" icon={Upload} label="Publish" onSelect={run(() => runFlowCommand('publish'))} className={row} />}
              {canManage && <PaletteAction id="run" icon={Play} label="Run the flow" shortcut="flow-run" onSelect={run(() => runFlowCommand('run'))} className={row} />}
              {canManage && nodes.length > 1 && <PaletteAction id="tidy" icon={LayoutTemplate} label="Tidy layout" hint="Line the steps up neatly" onSelect={run(tidyLayout)} className={row} />}
              {canManage && canUndo && <PaletteAction id="undo" icon={Undo2} label="Undo" hint={undoLabel} shortcut="flow-undo" onSelect={run(undo)} className={row} />}
              {canManage && canRedo && <PaletteAction id="redo" icon={Redo2} label="Redo" hint={redoLabel} shortcut="flow-redo" onSelect={run(redo)} className={row} />}
              {canManage && afterId && <PaletteAction id="duplicate" icon={Copy} label="Duplicate the selected step" shortcut="flow-duplicate" onSelect={run(() => actions.duplicate(selected))} className={row} />}
              {canManage && selected.length > 0 && <PaletteAction id="copy" icon={FileText} label={selected.length > 1 ? 'Copy the selected steps' : 'Copy the selected step'} shortcut="flow-copy" onSelect={run(() => actions.copy(selected))} className={row} />}
              {canManage && clip && <PaletteAction id="paste" icon={ClipboardPaste} label={`Paste ${clip.nodes.length === 1 ? '1 copied step' : `${clip.nodes.length} copied steps`}`} shortcut="flow-paste" onSelect={run(() => actions.paste())} className={row} />}
              <PaletteAction id="settings" icon={Settings} label="Flow settings" onSelect={run(() => runFlowCommand('settings'))} className={row} />
              <PaletteAction id="runs" icon={History} label="Run history" onSelect={run(() => runFlowCommand('runs'))} className={row} />
              <PaletteAction id="help" icon={CircleHelp} label="Help" onSelect={run(onOpenHelp)} className={row} />
              <PaletteAction id="shortcuts" icon={Keyboard} label="Keyboard shortcuts" hint="Every shortcut of the editor" onSelect={run(() => openShortcuts(true))} className={row} />
            </CommandGroup>

            {flowRows.length > 0 && (
              <CommandGroup heading={searching ? 'Open a flow' : 'Recent flows'} data-testid="flow-palette-flows">
                {flowRows.map((f) => (
                  <CommandItem
                    key={f.id}
                    value={`open flow ${f.name}`}
                    keywords={[f.id]}
                    className={row}
                    data-testid={`flow-palette-flow-${f.id}`}
                    onSelect={run(() => navigate(`/flows/${f.id}`))}
                  >
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                    <span className="min-w-0 flex-1 truncate font-medium">{f.name}</span>
                    <StatusPill kind={flowStatusKind(f.status)} />
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
          <div className="flex items-center gap-3 border-t border-border px-3 py-2 text-xs text-muted-foreground" aria-hidden>
            <span>Enter to choose</span>
            <span>Arrow keys to move</span>
            <span className="ml-auto">Esc to close</span>
          </div>
        </Command>
      </DialogContent>
    </Dialog>
  );
}

function PaletteAction({ id, icon: Icon, label, hint, shortcut, onSelect, className }: {
  id: string;
  icon: typeof Save;
  label: string;
  hint?: string;
  shortcut?: string;
  onSelect: () => void;
  className?: string;
}) {
  return (
    <CommandItem value={`${label}`} keywords={[hint ?? '', 'action']} className={cn(className)} data-testid={`flow-palette-action-${id}`} onSelect={onSelect}>
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium">{label}</span>
        {hint && <span className="block truncate text-xs text-muted-foreground">{hint}</span>}
      </span>
      {shortcut && <CommandShortcut className="shrink-0 tracking-normal">{shortcutText(shortcut)}</CommandShortcut>}
    </CommandItem>
  );
}
