import { Sparkles } from 'lucide-react';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { UseFormReturn } from 'react-hook-form';
import type { AgentFormValues } from './types';

interface BehaviorTabProps {
  form: UseFormReturn<AgentFormValues>;
  optimizingPrompt: boolean;
  onOptimizePrompt: () => void;
}

export function BehaviorTab({ form, optimizingPrompt, onOptimizePrompt }: BehaviorTabProps) {
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Conversation Settings</CardTitle>
          <CardDescription>Configure conversation behavior</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="allow_chat"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Allow Chat</FormLabel>
                  <FormDescription>
                    Enable in Chat window
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="persist_conversation"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Persist History</FormLabel>
                  <FormDescription>
                    Save conversation logs
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Instructions</CardTitle>
          <CardDescription>Define system prompt, goals, and constraints</CardDescription>
        </CardHeader>
        <CardContent className="relative">
          <FormField
            control={form.control}
            name="instructions"
            render={({ field }) => (
              <FormItem>
                <FormControl>
                  <Textarea
                    placeholder="Define system prompt, goals, constraints..."
                    className="min-h-[300px] font-mono resize-y"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="absolute top-6 right-10"
            onClick={onOptimizePrompt}
            disabled={optimizingPrompt}
          >
            <Sparkles className="w-4 h-4 mr-2" />
            {optimizingPrompt ? 'Optimizing...' : 'Optimize'}
          </Button>
        </CardContent>
      </Card>
    </>
  );
}

