import * as z from 'zod';

export const mcpFormSchema = z.object({
  server_name: z.string().min(1, 'Server name is required').optional(),
  enabled: z.boolean(),
  description: z.string().optional(),
  tool_namespace: z.string().optional(),
  timeout_seconds: z.number().int().positive().min(1, 'Timeout must be at least 1 second').optional(),
  transport_type: z.enum(['http', 'sse']),
  server_url: z.string().min(1, 'Server URL is required'),
  auth_type: z.enum(['none', 'api_key', 'bearer_token', 'custom_header']).optional(),
  auth_header_name: z.string().optional(),
  auth_header_value: z.string().optional(),
});

export type MCPFormValues = z.infer<typeof mcpFormSchema>;

