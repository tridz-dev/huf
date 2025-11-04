import { Badge } from '../ui/badge';
import { Checkbox } from '../ui/checkbox';
import { cn } from '@/lib/utils';
import type { AgentToolFunctionRef, AgentToolType } from '@/types/agent.types';

interface ToolCardProps {
  tool: AgentToolFunctionRef;
  selected?: boolean;
  onSelect?: (tool: AgentToolFunctionRef) => void;
  compact?: boolean;
  className?: string;
  toolTypesMap?: Map<string, AgentToolType>; // Map of tool_type name -> AgentToolType for lookup
}

export function ToolCard({
  tool,
  selected = false,
  onSelect,
  compact = false,
  className,
  toolTypesMap,
}: ToolCardProps) {
  const handleClick = () => {
    if (onSelect) {
      onSelect(tool);
    }
  };

  // Get tool type display name from tool_type link field
  const toolTypeDisplayName = tool.tool_type && toolTypesMap?.get(tool.tool_type)?.name1;

  return (
    <div
      onClick={handleClick}
      className={cn(
        'flex items-start gap-3 rounded-lg border p-3 transition-colors',
        'hover:bg-muted/50 cursor-pointer',
        selected && 'border-primary bg-primary/5',
        className
      )}
    >
      {onSelect && (
        <div className="pt-0.5" onClick={(e) => e.stopPropagation()}>
          <Checkbox
            checked={selected}
            onCheckedChange={() => onSelect(tool)}
          />
        </div>
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <h4 className="font-medium text-sm">{tool.tool_name || tool.name}</h4>
          {toolTypeDisplayName && (
            <Badge variant="outline" className="text-xs shrink-0">
              {toolTypeDisplayName}
            </Badge>
          )}
        </div>
        {tool.description && (
          <p className={cn(
            'text-muted-foreground',
            compact ? 'text-xs line-clamp-1' : 'text-xs line-clamp-2'
          )}>
            {tool.description}
          </p>
        )}
      </div>
    </div>
  );
}

