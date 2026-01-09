/**
 * MCP Server API functions
 * 
 * Provides frontend API for managing MCP server connections.
 */

import { db, call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import { doctype } from '@/data/doctypes';

/**
 * MCP Server document from Frappe
 */
export interface MCPServerDoc {
    name: string;
    server_name: string;
    description?: string;
    enabled: 0 | 1;
    transport_type: 'http' | 'sse';
    server_url: string;
    auth_type?: 'none' | 'api_key' | 'bearer_token' | 'custom_header';
    auth_header_name?: string;
    tool_namespace?: string;
    timeout_seconds?: number;
    last_sync?: string;
    available_tools?: string;
}

/**
 * MCP Server reference for agent child table
 */
export interface MCPServerRef {
    name: string;           // Child table row name
    mcp_server: string;     // Link to MCP Server DocType
    server_name?: string;   // Display name from MCP Server
    description?: string;   // Description from MCP Server
    server_url?: string;    // URL from MCP Server
    enabled: boolean | number;       // Whether enabled for this agent (0/1 from Frappe, boolean from frontend)
    mcp_enabled?: boolean | number;  // Whether the MCP Server itself is enabled (0/1 from Frappe, boolean from frontend)
    tool_count?: number;    // Number of tools available
    last_sync?: string;     // Last sync timestamp
}

/**
 * Pagination parameters for MCP servers
 */
export interface GetMCPServersParams {
    page?: number;
    limit?: number;
    start?: number;
    search?: string;
}

/**
 * Paginated response for MCP servers
 */
export interface PaginatedMCPServersResponse {
    items: MCPServerDoc[];
    hasMore: boolean;
    total?: number;
}

/**
 * Fetch all available MCP servers
 * Supports pagination and search
 */
export async function getMCPServers(
    params?: GetMCPServersParams
): Promise<PaginatedMCPServersResponse | MCPServerDoc[]> {
    try {
        // Backward compatibility: if no params, return array (old API)
        if (!params) {
            const response = await db.getDocList(doctype['MCP Server'], {
                fields: [
                    'name',
                    'server_name',
                    'description',
                    'enabled',
                    'transport_type',
                    'server_url',
                    'tool_namespace',
                    'timeout_seconds',
                    'last_sync',
                ],
                orderBy: { field: 'server_name', order: 'asc' },
                limit: 100,
            });
            return response as MCPServerDoc[];
        }

        const {
            page = 1,
            limit = 20,
            start = (page - 1) * limit,
            search,
        } = params;

        // Build filters
        const filters: Array<[string, string, unknown]> = [];

        // Build search filters if provided (search in server_name)
        if (search && search.trim()) {
            filters.push(['server_name', 'like', `%${search.trim()}%`]);
        }

        // Fetch data
        const servers = await db.getDocList(doctype['MCP Server'], {
            fields: [
                'name',
                'server_name',
                'description',
                'enabled',
                'transport_type',
                'server_url',
                'tool_namespace',
                'timeout_seconds',
                'last_sync',
            ],
            filters: filters.length > 0 ? (filters as any) : undefined,
            limit: limit + 1, // Fetch one extra to check if there's more
            ...(start > 0 && { limit_start: start }), // Only include if start > 0
            orderBy: { field: 'modified', order: 'desc' },
        });

        const mappedServers = servers as MCPServerDoc[];
        const hasMore = mappedServers.length > limit;
        const items = hasMore ? mappedServers.slice(0, limit) : mappedServers;

        // Only fetch count on first page to avoid unnecessary API calls
        let total: number | undefined;
        if (page === 1) {
            try {
                const { fetchDocCount } = await import('./utilsApi');
                const countFilters = [...filters];
                total = await fetchDocCount(doctype['MCP Server'], countFilters);
            } catch {
                // Ignore count errors - total is optional
            }
        }

        return {
            items,
            hasMore,
            total,
        };
    } catch (error) {
        handleFrappeError(error, 'Error fetching MCP servers');
    }
}

/**
 * Fetch a single MCP server by name
 */
export async function getMCPServer(name: string): Promise<MCPServerDoc> {
    try {
        const response = await db.getDoc(doctype['MCP Server'], name);
        return response as MCPServerDoc;
    } catch (error) {
        handleFrappeError(error);
        throw error;
    }
}

/**
 * Create a new MCP server
 */
export async function createMCPServer(data: Partial<MCPServerDoc>): Promise<MCPServerDoc> {
    try {
        const response = await db.createDoc(doctype['MCP Server'], data);
        return response as MCPServerDoc;
    } catch (error) {
        handleFrappeError(error);
        throw error;
    }
}

/**
 * Update an MCP server
 */
export async function updateMCPServer(name: string, data: Partial<MCPServerDoc>): Promise<MCPServerDoc> {
    try {
        const response = await db.updateDoc(doctype['MCP Server'], name, data);
        return response as MCPServerDoc;
    } catch (error) {
        handleFrappeError(error);
        throw error;
    }
}

/**
 * Delete an MCP server
 */
export async function deleteMCPServer(name: string): Promise<void> {
    try {
        await db.deleteDoc(doctype['MCP Server'], name);
    } catch (error) {
        handleFrappeError(error);
        throw error;
    }
}

/**
 * Get MCP servers linked to an agent
 */
export async function getAgentMCPServers(agentName: string): Promise<MCPServerRef[]> {
    try {
        const response = await call.post('huf.ai.mcp_client.get_agent_mcp_servers', {
            agent_name: agentName,
        });
        return (response.message || []) as MCPServerRef[];
    } catch (error) {
        handleFrappeError(error);
        throw error;
    }
}

/**
 * Get all available MCP servers (enabled ones)
 */
export async function getAvailableMCPServers(): Promise<MCPServerRef[]> {
    try {
        const response = await call.post('huf.ai.mcp_client.get_available_mcp_servers', {});
        return (response.message || []) as MCPServerRef[];
    } catch (error) {
        handleFrappeError(error);
        throw error;
    }
}

/**
 * Test connection to an MCP server
 */
export async function testMCPConnection(serverName: string): Promise<{ success: boolean; error?: string }> {
    try {
        const response = await call.post('huf.ai.mcp_client.test_mcp_connection', {
            server_name: serverName,
        });
        return response.message as { success: boolean; error?: string };
    } catch (error) {
        handleFrappeError(error);
        throw error;
    }
}

/**
 * Sync tools from an MCP server
 */
export async function syncMCPTools(serverName: string): Promise<{
    success: boolean;
    tool_count?: number;
    tools?: string[];
    error?: string;
}> {
    try {
        const response = await call.post('huf.ai.mcp_client.sync_mcp_server_tools', {
            server_name: serverName,
        });
        return response.message as { success: boolean; tool_count?: number; tools?: string[]; error?: string };
    } catch (error) {
        handleFrappeError(error);
        throw error;
    }
}
