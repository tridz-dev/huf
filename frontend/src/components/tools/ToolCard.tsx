import { Badge } from '../ui/badge';
import { Checkbox } from '../ui/checkbox';
import { cn } from '@/lib/utils';
import { presentToolName, summarizeDescription } from './toolPresentation';
import type { AgentToolFunctionRef } from '@/types/agent.types';
import { Users } from 'lucide-react';

interface ToolCardProps {
  tool: AgentToolFunctionRef;
  selected?: boolean;
  onSelect?: (tool: AgentToolFunctionRef) => void;
  className?: string;
  /** Agent names already using this tool. */
  usedByAgents?: string[];
}

export function ToolCard({
  tool,
  selected = false,
  onSelect,
  className,
  usedByAgents = [],
}: ToolCardProps) {
  const isShared = usedByAgents.length > 0;
  const handleClick = () => {
    if (onSelect) {
      onSelect(tool);
    }
  };

  const rawName = tool.tool_name || tool.name;
  // Lead with what the tool does, not how it was declared: the snake_case
  // function name becomes the headline, the service it talks to becomes a
  // chip, and the model-facing description is trimmed to its first sentence.
  const { title, provider } = presentToolName(rawName);
  const summary = summarizeDescription(tool.description);

  return (
    <div
      onClick={handleClick}
      onKeyDown={(e) => {
        if (onSelect && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          handleClick();
        }
      }}
      role={onSelect ? 'button' : undefined}
      tabIndex={onSelect ? 0 : undefined}
      aria-pressed={onSelect ? selected : undefined}
      className={cn(
        'flex items-start gap-3 rounded-lg border p-3 transition-colors',
        'hover:bg-paper-deep cursor-pointer',
        onSelect && 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        selected && 'border-primary bg-primary/5',
        className
      )}
    >
      {onSelect && (
        <div className="pt-0.5" onClick={(e) => e.stopPropagation()}>
          <Checkbox checked={selected} onCheckedChange={() => onSelect(tool)} />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="mb-0.5 flex flex-wrap items-center gap-2">
          <h4 className="text-sm font-medium">{title}</h4>
          {provider && (
            <Badge variant="outline" className="shrink-0 text-[10px]">
              {provider}
            </Badge>
          )}
          {isShared && (
            <Badge variant="secondary" className="flex shrink-0 items-center gap-1 text-[10px]">
              <Users className="h-3 w-3" aria-hidden="true" />
              Used by {usedByAgents.length} agent{usedByAgents.length > 1 ? 's' : ''}
            </Badge>
          )}
        </div>
        {summary && (
          <p className="text-xs text-muted-foreground line-clamp-2" title={tool.description}>
            {summary}
          </p>
        )}
        <p className="mt-1 font-mono text-[10px] text-steel-soft">{rawName}</p>
      </div>
    </div>
  );
}
