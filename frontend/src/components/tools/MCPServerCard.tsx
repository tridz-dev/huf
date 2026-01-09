import { Badge } from '../ui/badge';
import { Checkbox } from '../ui/checkbox';
import { cn } from '@/lib/utils';
import type { MCPServerDoc } from '@/services/mcpApi';

interface MCPServerCardProps {
  server: MCPServerDoc;
  selected?: boolean;
  onSelect?: (server: MCPServerDoc) => void;
  compact?: boolean;
  className?: string;
}

export function MCPServerCard({
  server,
  selected = false,
  onSelect,
  compact = false,
  className,
}: MCPServerCardProps) {
  const handleClick = () => {
    if (onSelect) {
      onSelect(server);
    }
  };

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
            onCheckedChange={() => onSelect(server)}
          />
        </div>
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <h4 className="font-medium text-sm">{server.server_name || server.name}</h4>
          {server.enabled === 1 ? (
            <Badge variant="default" className="text-xs shrink-0">enabled</Badge>
          ) : (
            <Badge variant="secondary" className="text-xs shrink-0">disabled</Badge>
          )}
        </div>
        {server.description && (
          <p className={cn(
            'text-muted-foreground',
            compact ? 'text-xs line-clamp-1' : 'text-xs line-clamp-2'
          )}>
            {server.description}
          </p>
        )}
        {server.server_url && (
          <p className={cn(
            'text-muted-foreground/70 mt-1',
            compact ? 'text-xs line-clamp-1' : 'text-xs truncate'
          )}>
            {server.server_url}
          </p>
        )}
      </div>
    </div>
  );
}

