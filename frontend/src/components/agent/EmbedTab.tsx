import type { UseFormReturn } from 'react-hook-form';

import type { AgentFormValues } from './types';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';

interface EmbedTabProps {
  form: UseFormReturn<AgentFormValues>;
}

export function EmbedTab({ form }: EmbedTabProps) {
  const embeddingEnabled = form.watch('embed_enabled');

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Embedding</CardTitle>
          <CardDescription>
            Allow this agent to be embedded on external websites using a publishable key.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <FormField
            control={form.control}
            name="embed_enabled"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-md border p-4">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Enable Embedding</FormLabel>
                  <FormDescription>
                    Allow this agent to be embedded on external websites using a publishable key.
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />

          {embeddingEnabled && (
            <div className="grid gap-6 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="publishable_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Publishable Key</FormLabel>
                    <FormControl>
                      <Input {...field} value={field.value ?? ''} readOnly />
                    </FormControl>
                    <FormDescription>
                      Auto-generated and safe to expose in client-side code. It is scoped to this agent.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="allowed_origins"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Allowed Origins</FormLabel>
                    <FormControl>
                      <Textarea
                        {...field}
                        value={field.value ?? ''}
                        placeholder="https://example.com"
                        rows={3}
                      />
                    </FormControl>
                    <FormDescription>
                      One origin per line. Requests from other origins will be rejected.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}