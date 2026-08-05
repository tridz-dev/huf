import { useState } from 'react';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { ChevronDown } from 'lucide-react';
import { UseFormReturn } from 'react-hook-form';
import type { MCPFormValues } from './types';

interface DetailsTabProps {
  form: UseFormReturn<MCPFormValues>;
  isNew: boolean;
}

export function DetailsTab({ form, isNew }: DetailsTabProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);

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
                <FormDescription>Unique identifier for this MCP server (e.g., &apos;gmail&apos;, &apos;github&apos;, &apos;frappe-erp&apos;)</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

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

        <Collapsible open={showAdvanced} onOpenChange={setShowAdvanced}>
          <CollapsibleTrigger asChild>
            <Button
              type="button"
              variant="outline"
              className="h-auto w-full items-center justify-between gap-4 rounded-lg p-4 text-left"
            >
              <div className="space-y-0.5">
                <p className="text-sm font-medium">Advanced</p>
                <p className="text-sm text-muted-foreground">
                  Tool namespace and request timeout. Usually not needed.
                </p>
              </div>
              <ChevronDown
                className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${showAdvanced ? 'rotate-180' : ''}`}
              />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="grid gap-6 pt-6">
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
                    <FormDescription>Request timeout for MCP server calls</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}
