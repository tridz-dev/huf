import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { UseFormReturn } from 'react-hook-form';
import type { MCPFormValues } from './types';

interface DetailsTabProps {
  form: UseFormReturn<MCPFormValues>;
  isNew: boolean;
}

export function DetailsTab({ form, isNew }: DetailsTabProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Server Details</CardTitle>
        <CardDescription>Configure MCP server basic information</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        {isNew && (
          <FormField
            control={form.control}
            name="server_name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Server Name</FormLabel>
                <FormControl>
                  <Input placeholder="my-mcp-server" {...field} />
                </FormControl>
                <FormDescription>Unique name for this MCP server</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        <FormField
          control={form.control}
          name="enabled"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
              <div className="space-y-0.5">
                <FormLabel className="text-base">Enabled</FormLabel>
                <FormDescription>
                  Enable or disable this MCP server
                </FormDescription>
              </div>
              <FormControl>
                <Switch
                  checked={field.value}
                  onCheckedChange={field.onChange}
                />
              </FormControl>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Description</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="What capabilities this MCP server provides"
                  className="min-h-[80px] resize-y"
                  {...field}
                />
              </FormControl>
              <FormDescription>What capabilities this MCP server provides</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="tool_namespace"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Tool Namespace</FormLabel>
              <FormControl>
                <Input placeholder="gmail" {...field} />
              </FormControl>
              <FormDescription>Optional prefix for tool names (e.g., 'gmail' results in 'gmail.send_email')</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="timeout_seconds"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Timeout (Seconds)</FormLabel>
              <FormControl>
                <Input
                  type="text"
                  placeholder="30"
                  {...field}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                />
              </FormControl>
              <FormDescription>Request timeout for MCP server calls (must be a positive integer)</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </CardContent>
    </Card>
  );
}

