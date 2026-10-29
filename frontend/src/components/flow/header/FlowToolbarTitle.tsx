import { useState, type KeyboardEvent } from 'react';
import { Pencil, Eye } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useFlowContext } from '@/contexts/FlowContext';
import { FLOW_VIEW_ONLY_HINT, useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { HIT_TARGET } from '@/lib/ui/responsive';
import { cn } from '@/lib/utils';

/**
 * Left-aligned "Flows > flow name [pencil]" control for the flow canvas toolbar. The name shrinks with the window (a tooltip
 * and the Settings dialog always carry the whole name) and on a phone gets the whole first row of the header.
 */
export function FlowToolbarTitle() {
  const { activeFlow, updateFlowName } = useFlowContext();
  const { canManage, roleNotApplied, readOnlyReason } = useFlowPermissions();
  const [isEditing, setIsEditing] = useState(false);
  const [draftName, setDraftName] = useState('');

  if (!activeFlow) {
    return <span className="text-ui-text text-steel truncate">Flows</span>;
  }

  const startEditing = () => {
    setDraftName(activeFlow.name);
    setIsEditing(true);
  };

  const commit = () => {
    setIsEditing(false);
    const trimmed = draftName.trim();
    if (trimmed && trimmed !== activeFlow.name) {
      void updateFlowName(activeFlow.id, trimmed);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      commit();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      setIsEditing(false);
    }
  };

  const nameWidth = 'max-w-[120px] min-[900px]:max-w-[170px] min-[1200px]:max-w-[240px] max-md:max-w-none';
  return (
    <div className="flex min-w-0 flex-1 items-center gap-1.5">
      <Link to="/flows" className="shrink-0 text-ui-text text-steel transition-colors hover:text-ink max-[899px]:hidden">
        Flows
      </Link>
      <span className="shrink-0 text-ui-text text-steel max-[899px]:hidden" aria-hidden>/</span>
      {isEditing ? (
        <Input
          value={draftName}
          onChange={(event) => setDraftName(event.target.value)}
          onBlur={commit}
          onKeyDown={handleKeyDown}
          autoFocus
          aria-label="Flow name"
          className={cn('h-control-sm min-w-0 border-0 px-1 py-0 text-ui-text font-medium text-ink focus-visible:ring-1', nameWidth)}
        />
      ) : (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span tabIndex={0} className={cn('truncate text-ui-text font-medium text-ink', nameWidth)} data-testid="flow-name">
                {activeFlow.name || 'Untitled flow'}
              </span>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-[320px] break-words">{activeFlow.name || 'Untitled flow'}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
      {canManage ? (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Edit flow name"
          onClick={startEditing}
          disabled={isEditing}
          className={cn('shrink-0 text-steel hover:text-ink', HIT_TARGET)}
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      ) : (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                tabIndex={0}
                className="inline-flex shrink-0 items-center gap-1 rounded-full border border-line bg-paper-deep px-2 py-0.5 text-xs font-medium text-steel"
                data-testid="flow-view-only-pill"
              >
                <Eye className="h-3 w-3" aria-hidden />
                View only
              </span>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-[260px]" data-testid="flow-view-only-pill-hint">
              {roleNotApplied ? readOnlyReason : FLOW_VIEW_ONLY_HINT}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </div>
  );
}
