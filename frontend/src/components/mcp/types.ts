import * as z from 'zod';

export const mcpFormSchema = z.object({
  server_name: z.string().min(1, 'Server name is required').optional(),
  enabled: z.boolean(),
  description: z.string().optional(),
  tool_namespace: z.string().optional(),
  timeout_seconds: z.number().int().positive().min(1, 'Timeout must be at least 1 second').optional(),
  transport_type: z.enum(['http', 'sse']),
  server_url: z.string().min(1, 'Server URL is required'),
  auth_type: z.enum(['none', 'api_key', 'bearer_token', 'custom_header', 'oauth']).optional(),
  auth_header_name: z.string().optional(),
  auth_header_value: z.string().optional(),
  oauth_status: z.string().optional(),
  oauth_scope: z.string().optional(),
  oauth_extra_authorize_params: z.string().optional(),
  oauth_redirect_uri: z.string().optional(),
  oauth_authorization_endpoint: z.string().optional(),
  oauth_token_endpoint: z.string().optional(),
  oauth_registration_endpoint: z.string().optional(),
  oauth_client_id: z.string().optional(),
  oauth_client_secret: z.string().optional(),
  oauth_discovery_status: z.string().optional(),
  oauth_resource_metadata_url: z.string().optional(),
  oauth_authorization_server: z.string().optional(),
  oauth_client_registration_method: z.string().optional(),
  oauth_metadata_json: z.string().optional(),
  oauth_last_discovered_at: z.string().optional(),
  oauth_discovery_error: z.string().optional(),
  auto_sync_interval: z.number().int().positive().min(1, 'Sync interval must be at least 1 hour').optional(),
  enable_auto_sync: z.boolean().optional(),
  custom_headers: z.array(
    z.object({
      header_name: z.string().min(1, 'Header name is required'),
      header_value: z.string().min(1, 'Header value is required'),
    })
  ).optional(),
});

export type MCPFormValues = z.infer<typeof mcpFormSchema>;

/**
 * Custom header row for an MCP server
 */
export interface MCPCustomHeader {
  header_name: string;
  header_value: string;
}

/**
 * MCP Tool from child table
 */
export interface MCPTool {
  name: string; // Child table row name
  tool_name: string; // Read-only
  description?: string; // Read-only
  parameters?: string; // Read-only, JSON string
  enabled: 0 | 1; // Editable
}

