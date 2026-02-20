import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { UseFormReturn } from 'react-hook-form';
import type { AgentFormValues } from './types';

interface AdvancedTabProps {
  form: UseFormReturn<AgentFormValues>;
}

export function AdvancedTab({ form }: AdvancedTabProps) {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Context Settings</CardTitle>
          <CardDescription>Configure how the agent handles conversation history and context</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="context_strategy"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Context Strategy</FormLabel>
                <Select onValueChange={field.onChange} value={field.value || ''}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select strategy" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="None">None</SelectItem>
                    <SelectItem value="Summarize">Summarize</SelectItem>
                    <SelectItem value="FIFO">FIFO</SelectItem>
                  </SelectContent>
                </Select>
                <FormDescription>
                  How to handle conversation history when it exceeds the limit. 'Summarize' compresses old messages, 'FIFO' drops them.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="summary_ratio"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Summary Ratio</FormLabel>
                <FormControl>
                  <Input
                    type="text"
                    placeholder="0.7"
                    {...field}
                    value={field.value?.toString() || ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      if (value === '') {
                        field.onChange(undefined);
                      } else {
                        const numValue = parseFloat(value);
                        if (!isNaN(numValue)) {
                          field.onChange(numValue);
                        }
                      }
                    }}
                  />
                </FormControl>
                <FormDescription>
                  Ratio of history to summarize effectively. 0.7 means 70% of oldest messages.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="history_limit"
            render={({ field }) => (
              <FormItem>
                <FormLabel>History Limit</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="50"
                    {...field}
                    value={field.value?.toString() || ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      if (value === '') {
                        field.onChange(undefined);
                      } else {
                        const numValue = parseInt(value, 10);
                        if (!isNaN(numValue)) {
                          field.onChange(numValue);
                        }
                      }
                    }}
                  />
                </FormControl>
                <FormDescription>
                  Maximum number of messages to keep in active context before applying strategy.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="max_knowledge_tokens"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Max Knowledge Tokens</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="2000"
                    {...field}
                    value={field.value?.toString() || ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      if (value === '') {
                        field.onChange(undefined);
                      } else {
                        const numValue = parseInt(value, 10);
                        if (!isNaN(numValue)) {
                          field.onChange(numValue);
                        }
                      }
                    }}
                  />
                </FormControl>
                <FormDescription>
                  Maximum tokens to use for injected knowledge context.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="max_turns"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Max Turns</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="10"
                    {...field}
                    value={field.value?.toString() || ''}
                    onChange={(e) => {
                      const value = e.target.value;
                      if (value === '') {
                        field.onChange(undefined);
                      } else {
                        const numValue = parseInt(value, 10);
                        if (!isNaN(numValue)) {
                          field.onChange(numValue);
                        }
                      }
                    }}
                  />
                </FormControl>
                <FormDescription>
                  Maximum consecutive turns/steps the agent can take in a single run.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="enable_conversation_data"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Allow Conversation Data Management</FormLabel>
                  <FormDescription>
                    If enabled, the agent can store key-value pairs in the conversation context.
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch
                    checked={field.value ?? false}
                    onCheckedChange={field.onChange}
                  />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="autonaming_of_conversation_title"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Autonaming of Conversation Title</FormLabel>
                  <FormDescription>
                    If enabled, the conversation title will be automatically updated based on the initial context.
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch
                    checked={field.value ?? false}
                    onCheckedChange={field.onChange}
                  />
                </FormControl>
              </FormItem>
            )}
          />
        </CardContent>
      </Card>
    </div>
  );
}
