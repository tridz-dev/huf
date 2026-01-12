import { useEffect } from 'react';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { UseFormReturn } from 'react-hook-form';
import type { MCPFormValues } from './types';
import { mcpAuthTypes, mcpAuthHeaderNames, mcpTransportTypes } from '@/data/mcp';

interface ConnectionTabProps {
  form: UseFormReturn<MCPFormValues>;
}

export function ConnectionTab({ form }: ConnectionTabProps) {
  const watchAuthType = form.watch('auth_type');

  // Auto-fill auth_header_name based on auth_type
  useEffect(() => {
    if (watchAuthType && watchAuthType !== 'none') {
      const headerName = mcpAuthHeaderNames[watchAuthType];
      if (headerName) {
        form.setValue('auth_header_name', headerName, { shouldDirty: false });
      }
    } else if (watchAuthType === 'none') {
      // Clear auth fields when auth_type is 'none'
      form.setValue('auth_header_name', '', { shouldDirty: false });
      form.setValue('auth_header_value', '', { shouldDirty: false });
    }
  }, [watchAuthType, form]);

  const showAuthFields = watchAuthType && watchAuthType !== 'none';

  return (
    <Card>
      <CardHeader>
        <CardTitle>Connection Settings</CardTitle>
        <CardDescription>Configure authentication and connection parameters</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        <FormField
          control={form.control}
          name="transport_type"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Transport Type</FormLabel>
              <Select
                onValueChange={field.onChange}
                value={field.value}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Select transport type" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {mcpTransportTypes.map((transportType) => (
                    <SelectItem key={transportType.value} value={transportType.value}>
                      {transportType.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>Communication protocol for MCP server</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="server_url"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Server URL</FormLabel>
              <FormControl>
                <Input
                  placeholder="https://mcp.example.com/mcp"
                  {...field}
                />
              </FormControl>
              <FormDescription>MCP server endpoint URL (e.g., 'https://mcp.example.com/mcp')</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="auth_type"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Authentication Type</FormLabel>
              <Select
                onValueChange={field.onChange}
                value={field.value || 'none'}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Select authentication type" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {mcpAuthTypes.map((authType) => (
                    <SelectItem key={authType.value} value={authType.value}>
                      {authType.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>Select the authentication method for this MCP server</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {showAuthFields && (
          <>
            <FormField
              control={form.control}
              name="auth_header_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Auth Header Name</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Authorization"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    Header name for authentication (e.g., 'Authorization', 'X-API-Key')
                    {watchAuthType !== 'custom_header' && ' (auto-filled based on auth type, but can be edited)'}
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="auth_header_value"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Auth Header Value</FormLabel>
                  <FormControl>
                    <Input
                      type="password"
                      placeholder="Enter API key, bearer token, or header value"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>The API key, bearer token, or header value (stored encrypted)</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}

