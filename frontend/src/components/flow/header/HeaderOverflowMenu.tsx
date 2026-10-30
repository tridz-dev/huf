import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { CircleHelp, History, Keyboard, LayoutTemplate, MoreHorizontal, Redo2, Search, Settings, ShieldAlert, Sparkles, Undo2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { StatusPill, type StatusKind } from '@/components/common/StatusPill';
import { FlowHelpDialog } from '../FlowHelpPopover';
import { ExecutionApprovalsBell } from '../../ExecutionApprovalsBell';
import { usePermissions } from '@/contexts/PermissionsContext';
import { useFlowContext } from '@/contexts/FlowContext';
import { useShortcutsHelp } from '@/components/shortcuts/ShortcutsHelpContext';
import { runFlowCommand } from '../shortcuts/flowCommands';
import { shortcutText } from '../shortcuts/shortcutHints';
import { HIT_TARGET } from '@/lib/ui/responsive';
import { cn } from '@/lib/utils';

interface HeaderOverflowMenuProps {
  statusKind: StatusKind;
  canManage: boolean;
  readOnlyReason: string | null;
  hasSteps: boolean;
  /** Id of the procedure this flow was saved as, when it was. */
  convertedProcedure: string | null;
  onOpenRuns: () => void;
  onOpenSettings: () => void;
  onTidy: () => void;
  onConvert: () => void;
  /** Extra first entries (the phone's "Show map / Show steps"). */
  extra?: ReactNode;
  /** The phone has no tidy / convert: those are editing tools. */
  editTools: boolean;
  /** 1201-1359px: the labelled buttons fit but the Help button does not, so the menu holds only "Help & shortcuts". */
  helpOnly?: boolean;
}

/**
 * The "..." menu of the editor header. At 1200px and narrower it holds what does not fit beside the labelled Run, Publish and
 * Save buttons: the flow's status, Help, Run history, Flow settings, Tidy layout and Convert to procedure. On a phone the same
 * menu (minus the editing tools) sits beside the Run button.
 */
export function HeaderOverflowMenu({
  statusKind, canManage, readOnlyReason, hasSteps, convertedProcedure, onOpenRuns, onOpenSettings, onTidy, onConvert, extra, editTools, helpOnly = false,
}: HeaderOverflowMenuProps) {
  const [showHelp, setShowHelp] = useState(false);
  const [showCodeApprovals, setShowCodeApprovals] = useState(false);
  const [codeApprovals, setCodeApprovals] = useState(0);
  const { hasCapability } = usePermissions();
  const canApproveCode = hasCapability('execution.approve') || hasCapability('ssh.approve');
  const { undo, redo, canUndo, canRedo, undoLabel, redoLabel } = useFlowContext();
  const { setOpen: openShortcuts } = useShortcutsHelp();
  const row = cn('gap-2', HIT_TARGET);
  const lower = (s?: string) => (s ? s.replace(/^./, (c) => c.toLowerCase()) : '');
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="icon" className={HIT_TARGET} aria-label="More actions" title="More actions" data-testid="flow-header-more">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[220px]" data-testid="flow-header-more-menu">
          {helpOnly ? (
            <DropdownMenuItem className={row} data-testid="flow-help" onSelect={() => setShowHelp(true)}>
              <CircleHelp className="h-4 w-4" aria-hidden /> Help &amp; shortcuts
            </DropdownMenuItem>
          ) : (<>
          <DropdownMenuLabel className="flex items-center justify-between gap-3 font-normal text-steel">
            This flow is
            <StatusPill kind={statusKind} data-testid="flow-status-pill-menu" />
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {extra}
          {editTools && canManage && (
            <>
              <DropdownMenuItem className={row} data-testid="flow-undo" disabled={!canUndo} title={canUndo ? `Undo: ${lower(undoLabel)}` : 'Nothing to undo yet'} onSelect={undo}>
                <Undo2 className="h-4 w-4" aria-hidden /> Undo{canUndo && undoLabel ? <span className="truncate text-xs text-muted-foreground">{lower(undoLabel)}</span> : null}
                <DropdownMenuShortcut>{shortcutText('flow-undo')}</DropdownMenuShortcut>
              </DropdownMenuItem>
              <DropdownMenuItem className={row} data-testid="flow-redo" disabled={!canRedo} title={canRedo ? `Redo: ${lower(redoLabel)}` : 'Nothing to redo'} onSelect={redo}>
                <Redo2 className="h-4 w-4" aria-hidden /> Redo
                <DropdownMenuShortcut>{shortcutText('flow-redo')}</DropdownMenuShortcut>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
            </>
          )}
          {editTools && (
            <DropdownMenuItem className={row} data-testid="flow-palette-open" onSelect={() => runFlowCommand('palette')}>
              <Search className="h-4 w-4" aria-hidden /> Search and commands
              <DropdownMenuShortcut>{shortcutText('flow-palette')}</DropdownMenuShortcut>
            </DropdownMenuItem>
          )}
          <DropdownMenuItem className={row} data-testid="flow-runs" onSelect={onOpenRuns}>
            <History className="h-4 w-4" aria-hidden /> Run history
          </DropdownMenuItem>
          <DropdownMenuItem className={row} data-testid="flow-settings" onSelect={onOpenSettings}>
            <Settings className="h-4 w-4" aria-hidden /> Flow settings
          </DropdownMenuItem>
          <DropdownMenuItem className={row} data-testid="flow-help" onSelect={() => setShowHelp(true)}>
            <CircleHelp className="h-4 w-4" aria-hidden /> Help &amp; shortcuts
          </DropdownMenuItem>
          {editTools && (
            <DropdownMenuItem className={row} data-testid="flow-shortcuts" onSelect={() => openShortcuts(true)}>
              <Keyboard className="h-4 w-4" aria-hidden /> Keyboard shortcuts
              <DropdownMenuShortcut>?</DropdownMenuShortcut>
            </DropdownMenuItem>
          )}
          {canApproveCode && (
            <DropdownMenuItem className={row} data-testid="flow-code-approvals" onSelect={() => setShowCodeApprovals(true)}>
              <ShieldAlert className="h-4 w-4" aria-hidden /> Code run approvals{codeApprovals > 0 ? ` (${codeApprovals})` : ''}
            </DropdownMenuItem>
          )}
          {editTools && hasSteps && (
            <DropdownMenuItem className={row} data-testid="flow-tidy-layout" disabled={!canManage} title={canManage ? undefined : readOnlyReason ?? undefined} onSelect={onTidy}>
              <LayoutTemplate className="h-4 w-4" aria-hidden /> Tidy layout
            </DropdownMenuItem>
          )}
          {editTools && convertedProcedure && (
            <DropdownMenuItem asChild className={row}>
              <Link to={`/procedures/${convertedProcedure}`} data-testid="flow-saved-as-procedure"><Sparkles className="h-4 w-4" aria-hidden /> Saved as procedure</Link>
            </DropdownMenuItem>
          )}
          {editTools && canManage && !convertedProcedure && (
            <DropdownMenuItem className={row} data-testid="flow-convert-to-procedure" onSelect={onConvert}>
              <Sparkles className="h-4 w-4" aria-hidden /> Convert to procedure
            </DropdownMenuItem>
          )}
          </>)}
        </DropdownMenuContent>
      </DropdownMenu>
      <FlowHelpDialog open={showHelp} onOpenChange={setShowHelp} />
      {canApproveCode && <ExecutionApprovalsBell variant="dialog" open={showCodeApprovals} onOpenChange={setShowCodeApprovals} onCount={setCodeApprovals} />}
    </>
  );
}
