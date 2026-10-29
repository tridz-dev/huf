import { useState } from 'react';
import { Copy, Info, MoreHorizontal, PowerOff, Power, Trash2, X } from 'lucide-react';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '../../ui/dropdown-menu';
import { Popover, PopoverContent, PopoverTrigger } from '../../ui/popover';
import { cardIcon } from '../../nodes/nodeIcons';
import { useFlowContext } from '../../../contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { actionCardId, actionLabel } from '@/lib/flow/flowLabels';
import type { FlowNode } from '../../../types/flow.types';
import { useFrame } from './frameStore';
import { Pressable } from './Pressable';
import { useViewport } from '@/lib/ui/responsive';
import { canDisableStep, canDuplicateStep, duplicateStep } from './stepActions';

/** The step's kind in small grey words under its name: "Trigger", "End", or what the step does ("Condition"). */
export function stepKindLabel(node: Pick<FlowNode, 'data'>): string {
  if (node.data.nodeType === 'trigger') return 'Trigger';
  if (node.data.nodeType === 'end') return 'End';
  return actionLabel(actionCardId(node.data.actionConfig as { type?: unknown; tool_id?: unknown } | undefined));
}

/**
 * 56px header of the step panel: icon, the step's name (the only place it appears; type to rename), its kind in small
 * grey type with an (i) for the longer explanation, a "..." menu and Close.
 */
export function StepHeader({ node, onClose, onDelete }: { node: FlowNode; onClose?: () => void; onDelete: () => void }) {
  const { updateNodeData, addNode, setSelectedNode } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const { isPhone } = useViewport();
  const hint = useFrame((s) => s.hint);
  const [menuOpen, setMenuOpen] = useState(false);
  const Icon = cardIcon(node.data);
  const duplicate = canDuplicateStep(node);
  const disable = canDisableStep(node);

  return (
    <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-border bg-card px-3.5" data-testid="flow-sidebar-header">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted text-foreground" aria-hidden>
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        <Input
          id="node-title"
          data-testid="flow-node-title-input"
          aria-label="Step name"
          title={node.data.label}
          value={node.data.label}
          readOnly={!canManage}
          placeholder="Name this step"
          onChange={(e) => updateNodeData(node.id, (data) => ({ ...data, label: e.target.value }))}
          size="sm"
          className="-mx-1 w-full min-w-0 truncate border-transparent px-1 text-ui-text font-semibold hover:border-border focus-visible:bg-background"
        />
        <div className="flex h-4 items-center gap-1 text-meta leading-none text-muted-foreground">
          <span className="truncate" data-testid="flow-sidebar-kind">{stepKindLabel(node)}</span>
          {hint ? (
            <Popover>
              <PopoverTrigger asChild>
                <Pressable
                  aria-label="About this step"
                  data-testid="flow-step-info"
                  className="inline-flex h-4 w-4 items-center justify-center rounded text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Info className="h-3 w-3" aria-hidden />
                </Pressable>
              </PopoverTrigger>
              <PopoverContent align="start" className="w-72 max-w-[calc(100vw-2rem)] text-xs leading-relaxed text-muted-foreground" data-testid="flow-config-hint">
                {hint}
              </PopoverContent>
            </Popover>
          ) : null}
        </div>
      </div>
      {canManage && !isPhone && (
        <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label="More actions for this step" data-testid="flow-step-menu" className="shrink-0 text-muted-foreground">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-44" data-testid="flow-step-menu-content">
            {duplicate && (
              <DropdownMenuItem
                data-testid="flow-step-duplicate"
                onSelect={() => {
                  const copy = duplicateStep(node);
                  addNode(copy);
                  setSelectedNode(copy.id);
                }}
              >
                <Copy className="mr-2 h-4 w-4" /> Duplicate
              </DropdownMenuItem>
            )}
            {disable && (
              <DropdownMenuItem
                data-testid="flow-step-disable"
                onSelect={() => updateNodeData(node.id, (data) => ({ ...data, disabled: !data.disabled }))}
              >
                {node.data.disabled ? <Power className="mr-2 h-4 w-4" /> : <PowerOff className="mr-2 h-4 w-4" />}
                {node.data.disabled ? 'Turn on' : 'Disable'}
              </DropdownMenuItem>
            )}
            {(duplicate || disable) && <DropdownMenuSeparator />}
            <DropdownMenuItem data-testid="flow-sidebar-delete" className="text-destructive focus:text-destructive" onSelect={onDelete}>
              <Trash2 className="mr-2 h-4 w-4" /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      {onClose && (
        <Button variant="ghost" size="icon-sm" aria-label="Close settings" data-testid="flow-sidebar-close" className="shrink-0 hover:bg-accent" onClick={onClose}>
          <X className="h-4 w-4 text-muted-foreground" />
        </Button>
      )}
    </div>
  );
}
