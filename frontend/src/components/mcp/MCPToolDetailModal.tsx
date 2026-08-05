import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { JsonViewer } from '@/components/ui/json-viewer';
import type { MCPTool } from './types';

interface MCPToolDetailModalProps {
  tool: MCPTool;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onToggle: (enabled: boolean) => void;
}

export function MCPToolDetailModal({
  tool,
  open,
  onOpenChange,
  onToggle,
}: MCPToolDetailModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[960px] max-h-[85vh] flex flex-col">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle>{tool.tool_name}</DialogTitle>
          <DialogDescription>Tool details and configuration</DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4 overflow-hidden flex flex-col min-h-0">
          {/* Enable/Disable Switch at the top */}
          <div className="flex items-center justify-between rounded-lg border p-4 flex-shrink-0">
            <div className="space-y-0.5">
              <Label className="text-base">Enabled</Label>
              <p className="text-sm text-steel">
                Enable or disable this tool for use with agents
              </p>
            </div>
            <Switch
              checked={tool.enabled === 1}
              onCheckedChange={onToggle}
            />
          </div>

          {/* Tool Name */}
          <div className="space-y-2 flex-shrink-0">
            <Label>Tool Name</Label>
            <div className="p-3 rounded-lg border bg-paper-deep/30">
              <p className="text-sm font-mono">{tool.tool_name}</p>
            </div>
          </div>

          {/* Description */}
          <div className="space-y-2 flex-shrink-0">
            <Label>Description</Label>
            <div className="p-3 rounded-lg border bg-paper-deep/30 min-h-[60px]">
              <p className="text-sm text-steel">
                {tool.description || 'No description available'}
              </p>
            </div>
          </div>

          {/* Parameters (JSON) - Only this section scrolls */}
          <div className="space-y-2 flex-1 min-h-0 flex flex-col">
            <Label className="flex-shrink-0">Parameters</Label>
            <div className="rounded-lg border overflow-hidden flex-1 min-h-0 flex flex-col">
              {tool.parameters ? (
                <div className="flex-1 overflow-y-auto min-h-0">
                  <JsonViewer value={tool.parameters} />
                </div>
              ) : (
                <div className="p-3 rounded-lg border bg-paper-deep/30 flex-shrink-0">
                  <p className="text-sm font-body text-steel-soft">No parameters defined</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

