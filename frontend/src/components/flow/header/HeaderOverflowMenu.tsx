import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { CircleHelp, History, LayoutTemplate, MoreHorizontal, Settings, ShieldAlert, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { StatusPill, type StatusKind } from '@/components/common/StatusPill';
import { FlowHelpDialog } from '../FlowHelpPopover';
import { ExecutionApprovalsBell } from '../../ExecutionApprovalsBell';
import { usePermissions } from '@/contexts/PermissionsContext';
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
}

/**
 * The "..." menu of the editor header. At 1200px and narrower it holds what does not fit beside the labelled Run, Publish and
 * Save buttons: the flow's status, Help, Run history, Flow settings, Tidy layout and Convert to procedure. On a phone the same
 * menu (minus the editing tools) sits beside the Run button.
 */
export function HeaderOverflowMenu({
  statusKind, canManage, readOnlyReason, hasSteps, convertedProcedure, onOpenRuns, onOpenSettings, onTidy, onConvert, extra, editTools,
}: HeaderOverflowMenuProps) {
  const [showHelp, setShowHelp] = useState(false);
  const [showCodeApprovals, setShowCodeApprovals] = useState(false);
  const [codeApprovals, setCodeApprovals] = useState(0);
  const { hasCapability } = usePermissions();
  const canApproveCode = hasCapability('execution.approve') || hasCapability('ssh.approve');
  const row = cn('gap-2', HIT_TARGET);
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="icon" className={HIT_TARGET} aria-label="More actions" title="More actions" data-testid="flow-header-more">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[220px]" data-testid="flow-header-more-menu">
          <DropdownMenuLabel className="flex items-center justify-between gap-3 font-normal text-steel">
            This flow is
            <StatusPill kind={statusKind} data-testid="flow-status-pill-menu" />
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {extra}
          <DropdownMenuItem className={row} data-testid="flow-runs" onSelect={onOpenRuns}>
            <History className="h-4 w-4" aria-hidden /> Run history
          </DropdownMenuItem>
          <DropdownMenuItem className={row} data-testid="flow-settings" onSelect={onOpenSettings}>
            <Settings className="h-4 w-4" aria-hidden /> Flow settings
          </DropdownMenuItem>
          <DropdownMenuItem className={row} data-testid="flow-help" onSelect={() => setShowHelp(true)}>
            <CircleHelp className="h-4 w-4" aria-hidden /> Help
          </DropdownMenuItem>
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
        </DropdownMenuContent>
      </DropdownMenu>
      <FlowHelpDialog open={showHelp} onOpenChange={setShowHelp} />
      {canApproveCode && <ExecutionApprovalsBell variant="dialog" open={showCodeApprovals} onOpenChange={setShowCodeApprovals} onCount={setCodeApprovals} />}
    </>
  );
}
