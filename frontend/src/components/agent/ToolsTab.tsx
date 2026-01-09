import { Plus, Server, Plug, Trash2, RefreshCw } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { AgentToolFunctionRef, AgentToolType } from '@/types/agent.types';
import type { MCPServerRef } from '@/services/mcpApi';

interface ToolsTabProps {
  selectedTools: AgentToolFunctionRef[];
  toolTypes: AgentToolType[];
  onAddTools: () => void;
  onRemoveTool: (toolId: string) => void;
  // MCP Server props
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
    switch (action) {
      case 'add':
        onAddMCP?.();
        break;
      case 'remove':
        if (serverId) {
          onRemoveMCP?.(serverId);
        }
        break;
      case 'toggle':
        if (serverId && onToggleMCP) {
          const server = mcpServers.find(s => s.name === serverId);
          if (server) {
            // Toggle the enabled state - normalize current value first
            const currentEnabled = isEnabled(server.enabled);
            onToggleMCP(serverId, !currentEnabled);
          }
        }
        break;
      case 'sync':
        if (serverId) {
          onSyncMCP?.(serverId);
        }
        break;
    }
  };

  // Helper to normalize enabled state (handles both boolean and number 0/1)
  // If undefined, defaults to true (assume enabled if not specified)
  const isEnabled = (value: boolean | number | undefined): boolean => {
    if (value === undefined) return true; // Default to enabled if not specified
    return value === true || value === 1;
  };

  const getStatusBadge = (server: MCPServerRef) => {
    const agentEnabled = isEnabled(server.enabled);
    
    // If MCP server itself is explicitly disabled (not undefined), show "server disabled"
    if (server.mcp_enabled !== undefined && !isEnabled(server.mcp_enabled)) {
      return <Badge variant="secondary" className="text-xs shrink-0">server disabled</Badge>;
    }
    // If MCP server is enabled (or unknown) but agent has it disabled, show "disabled"
    if (!agentEnabled) {
      return <Badge variant="secondary" className="text-xs shrink-0">disabled</Badge>;
    }
    // Both enabled - show "connected"
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
            <div className="">
              {mcpServers.map((mcp) => (
                <div
                  key={mcp.name}
                  className="flex items-start justify-between gap-3 rounded-lg border p-4 hover:bg-muted/50 transition-colors"
                >
                  <Link 
                    to={`/mcp/${mcp.mcp_server}`}
                    className="flex-1 min-w-0 overflow-hidden cursor-pointer"
                  >
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
                        <p className="text-xs text-muted-foreground mt-1" title={mcp.server_url}>
                          {mcp.server_url}
                        </p>
                      )}
                  </Link>
                  <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleMCPAction('sync', mcp.name)}
                      disabled={mcpLoading || (mcp.mcp_enabled !== undefined && !isEnabled(mcp.mcp_enabled))}
                      title="Sync tools from MCP server"
                    >
                      <RefreshCw className={`w-4 h-4 ${mcpLoading ? 'animate-spin' : ''}`} />
                    </Button>
                    <Switch
                      checked={isEnabled(mcp.enabled)}
                      disabled={mcpLoading || (mcp.mcp_enabled !== undefined && !isEnabled(mcp.mcp_enabled))}
                      onCheckedChange={() => {
                        // Only allow toggle if MCP server is enabled (or unknown/undefined)
                        if (!mcpLoading && (mcp.mcp_enabled === undefined || isEnabled(mcp.mcp_enabled))) {
                          handleMCPAction('toggle', mcp.name);
                        }
                      }}
                    />
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