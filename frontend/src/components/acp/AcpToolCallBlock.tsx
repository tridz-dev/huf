import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Terminal, ChevronRight } from 'lucide-react';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { ToolInput, ToolOutput } from '@/components/ai-elements/tool';
import type { ToolUIPart } from 'ai';

interface AcpToolCallBlockProps {
  tool: {
    tool_call_id: string;
    name: string;
    description: string;
    status: ToolUIPart['state'];
    parameters: Record<string, unknown>;
    result: string | undefined;
    error: string | undefined;
    durationMs?: number;
  };
}

const STATUS_LABELS: Record<ToolUIPart['state'], string> = {
  'input-streaming': 'pending',
  'input-available': 'running',
  'approval-requested': 'needs approval',
  'approval-responded': 'responded',
  'output-available': 'done',
  'output-error': 'failed',
  'output-denied': 'denied',
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function AcpToolCallBlock({ tool }: AcpToolCallBlockProps) {
  const [open, setOpen] = useState(false);
  const connectionName =
    (tool.parameters?.connection_name as string | undefined) || tool.name;
  const prompt = (tool.parameters?.prompt as string | undefined) || '';
  const isFailed = tool.status === 'output-error';

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="not-prose mb-1 w-full">
      <div className="flex items-center gap-2">
        <CollapsibleTrigger
          className={cn(
            'group flex min-w-0 flex-1 items-center gap-1.5 rounded-[7px] px-[7px] py-[3px] -ml-[7px] text-left leading-[24px] transition-colors hover:bg-muted/60'
          )}
        >
          <Terminal
            className={cn(
              'size-[13px] shrink-0',
              isFailed ? 'text-destructive' : 'text-muted-foreground'
            )}
          />
          <span className="truncate font-mono text-[12px] text-foreground">
            Called {connectionName}
          </span>
          <span className="shrink-0 text-muted-foreground/50">&middot;</span>
          <span
            className={cn(
              'shrink-0 text-[12px]',
              isFailed ? 'text-destructive' : 'text-muted-foreground'
            )}
          >
            {STATUS_LABELS[tool.status]}
          </span>
          {tool.durationMs !== undefined && (
            <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
              {formatDuration(tool.durationMs)}
            </span>
          )}
          <ChevronRight className="ml-auto size-[13px] shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" />
        </CollapsibleTrigger>
        <Link
          to="/acp-connections"
          target="_blank"
          className="shrink-0 text-[11px] text-muted-foreground hover:text-foreground hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          View connection
        </Link>
      </div>
      <CollapsibleContent
        className={cn(
          'mt-1 space-y-2 border-line/60 border-l pl-3 text-popover-foreground outline-none',
          'data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2 data-[state=closed]:animate-out data-[state=open]:animate-in'
        )}
      >
        <ToolInput input={tool.parameters} />
        <ToolOutput output={tool.result} errorText={tool.error} />
        {prompt && !tool.result && !tool.error && (
          <div className="text-xs text-steel-soft">
            Prompt: {prompt}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
