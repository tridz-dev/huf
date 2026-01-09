import { Plus, Server, Plug, Trash2, RefreshCw, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';
import type { AgentToolFunctionRef, AgentToolType } from '@/types/agent.types';

/**
 * MCP Server reference as stored in agent_mcp_server child table
 */
export interface MCPServerRef {
  name: string;           // Child table row name
  mcp_server: string;     // Link to MCP Server DocType
  server_name?: string;   // Display name from MCP Server
  description?: string;   // Description from MCP Server
  server_url?: string;    // URL from MCP Server
  enabled: boolean;       // Whether enabled for this agent
  mcp_enabled?: boolean;  // Whether the MCP Server itself is enabled
  tool_count?: number;    // Number of tools available
  last_sync?: string;     // Last sync timestamp
}

interface ToolsTabProps {
  selectedTools: AgentToolFunctionRef[];
  toolTypes: AgentToolType[];
  onAddTools: () => void;
  onRemoveTool: (toolId: string) => void;
  // MCP Server props - optional for backward compatibility
  mcpServers?: MCPServerRef[];
  onAddMCP?: () => void;
  onRemoveMCP?: (serverId: string) => void;
  onToggleMCP?: (serverId: string, enabled: boolean) => void;
  onSyncMCP?: (serverId: string) => void;
  mcpLoading?: boolean;
}

export function ToolsTab({
  selectedTools,
  toolTypes,
  onAddTools,
  onRemoveTool,
  mcpServers = [],
  onAddMCP,
  onRemoveMCP,
  onToggleMCP,
  onSyncMCP,
  mcpLoading = false,
}: ToolsTabProps) {

  const handleMCPAction = (action: string, serverId?: string) => {
    // If no handler provided, show "coming soon"
    switch (action) {
      case 'add':
        if (onAddMCP) {
          onAddMCP();
        } else {
          toast.info('MCP server management coming soon');
        }
        break;
      case 'remove':
        if (serverId && onRemoveMCP) {
          onRemoveMCP(serverId);
        } else {
          toast.info('MCP server management coming soon');
        }
        break;
      case 'toggle':
        if (serverId && onToggleMCP) {
          const server = mcpServers.find(s => s.name === serverId);
          if (server) {
            onToggleMCP(serverId, !server.enabled);
          }
        } else {
          toast.info('MCP server management coming soon');
        }
        break;
      case 'sync':
        if (serverId && onSyncMCP) {
          onSyncMCP(serverId);
        } else {
          toast.info('MCP server sync coming soon');
        }
        break;
    }
  };

  const getStatusBadge = (server: MCPServerRef) => {
    if (!server.mcp_enabled) {
      return <Badge variant="destructive" className="text-xs shrink-0">server disabled</Badge>;
    }
    if (!server.enabled) {
      return <Badge variant="secondary" className="text-xs shrink-0">inactive</Badge>;
    }
    return <Badge variant="default" className="text-xs shrink-0">connected</Badge>;
  };

  return (
    <>
      {/* Native Tools Section */}
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

      {/* MCP Servers Section */}
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
              onClick={() => handleMCPAction('add')}
              disabled={mcpLoading}
            >
              <Plus className="w-4 h-4 mr-2" />
              Connect MCP
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {mcpServers.length === 0 ? (
            <div className="text-center py-8">
              <div className="flex justify-center mb-4">
                <div className="rounded-full bg-muted p-3">
                  <Plug className="w-6 h-6 text-muted-foreground" />
                </div>
              </div>
              <p className="text-muted-foreground mb-2">No MCP servers connected</p>
              <p className="text-xs text-muted-foreground mb-4">
                Connect external MCP servers to extend agent capabilities with tools like Gmail, GitHub, Slack, and more.
              </p>
              <Button
                variant="outline"
                type="button"
                onClick={() => handleMCPAction('add')}
              >
                <Plus className="w-4 h-4 mr-2" />
                Connect MCP Server
              </Button>
            </div>
          ) : (
            <div className="grid gap-3">
              {mcpServers.map((mcp) => (
                <div
                  key={mcp.name}
                  className="flex items-start justify-between gap-3 rounded-lg border p-4 hover:bg-muted/50 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <h4 className="font-medium text-sm">{mcp.server_name || mcp.mcp_server}</h4>
                      {getStatusBadge(mcp)}
                      {mcp.tool_count !== undefined && mcp.tool_count > 0 && (
                        <Badge variant="outline" className="text-xs shrink-0">
                          {mcp.tool_count} tools
                        </Badge>
                      )}
                    </div>
                    {mcp.description && (
                      <p className="text-xs text-muted-foreground">{mcp.description}</p>
                    )}
                    {mcp.server_url && (
                      <p className="text-xs text-muted-foreground/70 mt-1 truncate">
                        {mcp.server_url}
                      </p>
                    )}
                    {!mcp.mcp_enabled && (
                      <div className="flex items-center gap-1 mt-2 text-xs text-amber-600">
                        <AlertCircle className="w-3 h-3" />
                        <span>MCP server is disabled globally</span>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleMCPAction('sync', mcp.name)}
                      disabled={mcpLoading || !mcp.mcp_enabled}
                      title="Sync tools from MCP server"
                    >
                      <RefreshCw className={`w-4 h-4 ${mcpLoading ? 'animate-spin' : ''}`} />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleMCPAction('toggle', mcp.name)}
                      disabled={mcpLoading || !mcp.mcp_enabled}
                      title={mcp.enabled ? 'Disable for this agent' : 'Enable for this agent'}
                    >
                      <Switch
                        checked={mcp.enabled && mcp.mcp_enabled !== false}
                        className="pointer-events-none"
                      />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleMCPAction('remove', mcp.name)}
                      disabled={mcpLoading}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
