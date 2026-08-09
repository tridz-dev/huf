import { Zap, Bot, GitBranch, Wrench, Database, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from './ui/tooltip';
import type { ActionOption } from '../types/modal.types';

/**
 * Categories addressable from the node palette rail.
 * `trigger` opens the modal in trigger mode; every other entry opens it in
 * action mode pre-filtered to the matching `ActionOption['category']`.
 */
export type NodeRailCategory = 'trigger' | 'agent' | 'condition' | 'tool' | 'data';

export const NODE_RAIL_ACTION_CATEGORY: Record<
  Exclude<NodeRailCategory, 'trigger'>,
  ActionOption['category']
> = {
  agent: 'agent',
  condition: 'control',
  tool: 'tool',
  data: 'integration',
};

interface RailItem {
  id: NodeRailCategory;
  label: string;
  icon: LucideIcon;
}

const RAIL_ITEMS: RailItem[] = [
  { id: 'trigger', label: 'Trigger', icon: Zap },
  { id: 'agent', label: 'Agent', icon: Bot },
  { id: 'condition', label: 'Condition', icon: GitBranch },
  { id: 'tool', label: 'Tool', icon: Wrench },
  { id: 'data', label: 'Data', icon: Database },
];

export interface FlowNodeRailProps {
  /** Category highlighted as active, e.g. derived from the selected node. */
  activeCategory?: NodeRailCategory | null;
  /** Categories that cannot be added right now (e.g. no trigger exists yet). */
  disabledCategories?: NodeRailCategory[];
  onSelect: (category: NodeRailCategory) => void;
}

/**
 * Persistent 48px node-palette rail pinned to the left edge of the flow
 * editor's canvas area. Icon-only quick access to the node categories that
 * the NodeSelectionModal already exposes.
 */
export function FlowNodeRail({
  activeCategory,
  disabledCategories,
  onSelect,
}: FlowNodeRailProps) {
  return (
    <TooltipProvider delayDuration={200}>
      <div
        role="toolbar"
        aria-orientation="vertical"
        aria-label="Node palette"
        className="flex h-full w-12 shrink-0 flex-col items-center gap-1 border-r border-line bg-paper py-3"
      >
        {RAIL_ITEMS.map(({ id, label, icon: Icon }) => {
          const isActive = activeCategory === id;
          const isDisabled = disabledCategories?.includes(id) ?? false;
          return (
            <Tooltip key={id}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label={`Add ${label} node`}
                  aria-pressed={isActive}
                  disabled={isDisabled}
                  onClick={() => onSelect(id)}
                  className={cn(
                    'flex h-[30px] w-[30px] items-center justify-center rounded-[8px]',
                    'text-steel transition-colors duration-150',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal focus-visible:ring-offset-1 focus-visible:ring-offset-paper',
                    isActive
                      ? 'bg-paper-deep text-ink'
                      : 'bg-transparent hover:bg-paper-deep hover:text-ink',
                    isDisabled && 'pointer-events-none opacity-40'
                  )}
                >
                  <Icon className="h-4 w-4" strokeWidth={1.75} />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">{label}</TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
