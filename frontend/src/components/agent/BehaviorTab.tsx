import { FormField, FormItem, FormLabel, FormControl, FormDescription } from '@/components/ui/form';
import { Switch } from '@/components/ui/switch';
import { UseFormReturn } from 'react-hook-form';
import type { AgentFormValues } from './types';
import { toast } from 'sonner';
import { SectionRailLayout, SectionBlock, type RailSection } from './form-base/SectionRailLayout';

interface BehaviorTabProps {
  form: UseFormReturn<AgentFormValues>;
}

export function BehaviorTab({ form }: BehaviorTabProps) {
  const persistConversationEnabled = form.watch('persist_conversation');
  const enableMultiRun = form.watch('enable_multi_run');
  const allowChat = form.watch('allow_chat');
  const persistPerUser = form.watch('persist_user_history');

  const sections: RailSection[] = [
    {
      id: 'chat',
      label: 'Chat Access',
      status: allowChat ? 'complete' : 'partial',
      meta: allowChat ? 'Enabled' : 'Disabled',
    },
    {
      id: 'history',
      label: 'History',
      status: persistConversationEnabled ? 'complete' : 'empty',
      meta: persistConversationEnabled ? (persistPerUser ? 'Per user' : 'Shared') : 'Not persisted',
    },
    {
      id: 'execution',
      label: 'Execution',
      status: enableMultiRun ? 'complete' : 'partial',
      meta: enableMultiRun ? 'Multi run enabled' : 'Single run mode',
    },
  ];

  return (
    <SectionRailLayout sections={sections}>
      <SectionBlock id="chat" title="Chat Access" description="Control whether this agent is available in Agent Chat.">
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
      </SectionBlock>

      <SectionBlock id="history" title="History" description="Save and segment conversation history.">
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="persist_conversation"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Persist History</FormLabel>
                  <FormDescription>
                    Save and load conversation history for future sessions.
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
                    Keep histories isolated by initiating user (otherwise one shared history is used).
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />
        </div>
      </SectionBlock>

      <SectionBlock id="execution" title="Execution" description="Multi-run mode settings.">
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
      </SectionBlock>
    </SectionRailLayout>
  );
}
