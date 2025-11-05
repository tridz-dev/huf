import { Plus, Server, Plug, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';
import type { AgentToolFunctionRef, AgentToolType } from '@/types/agent.types';

interface MCPItem {
  id: string;
  name: string;
  description: string;
  provider: string;
  status: 'connected' | 'inactive';
}

const mockMCPs: MCPItem[] = [
  { id: 'm1', name: 'Zendesk MCP', description: 'Query and manage Zendesk tickets', provider: 'Zendesk', status: 'connected' },
  { id: 'm2', name: 'Slack MCP', description: 'Send messages and read channels', provider: 'Slack', status: 'connected' },
  { id: 'm3', name: 'PostgreSQL MCP', description: 'Query customer database', provider: 'PostgreSQL', status: 'connected' },
  { id: 'm4', name: 'Stripe MCP', description: 'Access payment and subscription data', provider: 'Stripe', status: 'inactive' },
];

interface ToolsTabProps {
  selectedTools: AgentToolFunctionRef[];
  toolTypes: AgentToolType[];
  onAddTools: () => void;
  onRemoveTool: (toolId: string) => void;
}

export function ToolsTab({
  selectedTools,
  toolTypes,
  onAddTools,
  onRemoveTool,
}: ToolsTabProps) {
  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Server className="w-5 h-5" />
                Tools
              </CardTitle>
              <CardDescription>Function tools available to this agent</CardDescription>
            </div>
            <Button size="sm" variant="outline" onClick={onAddTools} type="button">
              <Plus className="w-4 h-4 mr-2" />
              Add Tool
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {selectedTools.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground mb-4">No tools added yet.</p>
              <Button onClick={onAddTools} variant="outline" type="button">
                <Plus className="w-4 h-4 mr-2" />
                Add Tool
              </Button>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {selectedTools.map((tool) => {
                const toolType = toolTypes.find((tt) => tt.name === tool.tool_type);
                const toolTypeDisplayName = toolType?.name1;

                return (
                  <div
                    key={tool.name}
                    className="flex items-start justify-between gap-3 rounded-lg border p-4 hover:bg-muted/50 transition-colors"
                  >
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
                        <p className="text-xs text-muted-foreground">{tool.description}</p>
                      )}
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => onRemoveTool(tool.name)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Plug className="w-5 h-5" />
                Model Context Protocol (MCP)
              </CardTitle>
              <CardDescription>Connected MCP servers for extended capabilities</CardDescription>
            </div>
            <Button 
              type="button"
              size="sm" 
              variant="outline"
              onClick={() => toast.info('Coming soon')}
            >
              <Plus className="w-4 h-4 mr-2" />
              Connect MCP
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3">
            {mockMCPs.map((mcp) => (
              <div
                key={mcp.id}
                className="flex items-start justify-between gap-3 rounded-lg border p-4 hover:bg-muted/50 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="font-medium text-sm">{mcp.name}</h4>
                    <Badge variant="outline" className="text-xs shrink-0">
                      {mcp.provider}
                    </Badge>
                    <Badge
                      variant={mcp.status === 'connected' ? 'default' : 'secondary'}
                      className="text-xs shrink-0"
                    >
                      {mcp.status}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">{mcp.description}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => toast.info('Coming soon')}
                  >
                    <Switch checked={mcp.status === 'connected'} className="pointer-events-none" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => toast.info('Coming soon')}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </>
  );
}

