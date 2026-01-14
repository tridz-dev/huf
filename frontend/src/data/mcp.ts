/**
 * MCP Server configuration constants
 * These values can later be fetched from an API if needed
 */

export const mcpAuthTypes = [
  { label: 'None', value: 'none' },
  { label: 'API Key', value: 'api_key' },
  { label: 'Bearer Token', value: 'bearer_token' },
  { label: 'Custom Header', value: 'custom_header' },
] as const;

export type MCPAuthType = typeof mcpAuthTypes[number]['value'];

export const mcpAuthHeaderNames: Record<MCPAuthType, string> = {
  none: '',
  api_key: 'X-API-Key',
  bearer_token: 'Authorization',
  custom_header: 'Authorization',
} as const;

/**
 * Default header value prefix for bearer token
 * The actual token value will be prepended to this
 */
export const mcpAuthHeaderValuePrefix: Record<MCPAuthType, string> = {
  none: '',
  api_key: '',
  bearer_token: 'Bearer ',
  custom_header: '',
} as const;

export const mcpTransportTypes = [
  { label: 'HTTP/HTTPS', value: 'http' },
  { label: 'SSE (Server-Sent Events)', value: 'sse' },
] as const;

export type MCPTransportType = typeof mcpTransportTypes[number]['value'];

