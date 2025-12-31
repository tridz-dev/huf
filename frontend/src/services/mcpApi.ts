/**
 * MCP Server API functions
 * 
 * Provides frontend API for managing MCP server connections.
 */

import { db, call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

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
    enabled: boolean;       // Whether enabled for this agent
    mcp_enabled?: boolean;  // Whether the MCP Server itself is enabled
    tool_count?: number;    // Number of tools available
    last_sync?: string;     // Last sync timestamp
}

/**
 * Fetch all available MCP servers
 */
export async function getMCPServers(): Promise<MCPServerDoc[]> {
    try {
        const response = await db.getDocList('MCP Server', {
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
    } catch (error) {
        handleFrappeError(error);
        throw error;
    }
}

/**
 * Fetch a single MCP server by name
 */
export async function getMCPServer(name: string): Promise<MCPServerDoc> {
    try {
        const response = await db.getDoc('MCP Server', name);
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
        const response = await db.createDoc('MCP Server', data);
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
        const response = await db.updateDoc('MCP Server', name, data);
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
        await db.deleteDoc('MCP Server', name);
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
