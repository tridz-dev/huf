import { FormField, FormItem, FormLabel, FormControl, FormDescription } from '@/components/ui/form';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { UseFormReturn } from 'react-hook-form';
import type { AgentFormValues } from './types';
import { toast } from 'sonner';

interface BehaviorTabProps {
  form: UseFormReturn<AgentFormValues>;
}

export function BehaviorTab({ form }: BehaviorTabProps) {
  const persistConversationEnabled = form.watch('persist_conversation');
  const enableMultiRun = form.watch('enable_multi_run');

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
                    If checked, this agent can be interacted with in the Agent Chat window.
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch
                    checked={field.value}
                    disabled={enableMultiRun}
                    onCheckedChange={(checked) => {
                      if (enableMultiRun) {
                        toast.warning('Chat is not available for multi run agents right now.');
                        return;
                      }
                      if (checked && !persistConversationEnabled) {
                        toast.warning('Turn on Persist History before enabling chat.');
                        return;
                      }
                      field.onChange(checked);
                    }}
                  />
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
                    If checked, the conversation history with this agent will be saved and loaded for future sessions.
                  </FormDescription>
                </div>
                <FormControl className="ml-1">
                  <Switch
                    checked={field.value}
                    onCheckedChange={(checked) => {
                      field.onChange(checked);
                      if (!checked) {
                        form.setValue('allow_chat', false, { shouldDirty: true });
                      }
                    }}
                  />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="persist_user_history"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Persist per User (Doc/Schedule)</FormLabel>
                  <FormDescription>
                    When checked, Doc Event and Scheduled runs create / maintain conversation history per
                    initiating user (or trigger owner). If unchecked, a single shared history is used.
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
            name="enable_multi_run"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Enable Multi Run</FormLabel>
                  <FormDescription>
                    When enabled, this agent can execute multiple runs.
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch
                    checked={field.value}
                    onCheckedChange={(checked) => {
                      field.onChange(checked);
                      if (checked) {
                        // Disable chat when multi run is enabled
                        const currentChatValue = form.getValues('allow_chat');
                        if (currentChatValue) {
                          form.setValue('allow_chat', false, { shouldDirty: true });
                        }
                      }
                    }}
                  />
                </FormControl>
              </FormItem>
            )}
          />
        </CardContent>
      </Card>
    </>
  );
}

