import {
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription
} from '@/components/ui/form'

import { Switch } from '@/components/ui/switch'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { UseFormReturn } from 'react-hook-form'
import type { AgentFormValues } from './types'
import { toast } from 'sonner'

interface BehaviorTabProps {
  form: UseFormReturn<AgentFormValues>
}

export function BehaviorTab({ form }: BehaviorTabProps) {
  const persistConversationEnabled = form.watch('persist_conversation')
  const enableMultiRun = form.watch('enable_multi_run')

  const defaultPlan = form.watch('default_plan') || []

  const addStep = () => {
    const current = form.getValues('default_plan') || []

    form.setValue('default_plan', [
      ...current,
      {
        step_index: current.length + 1,
        status: 'pending',
        instruction: '',
        output_ref: ''
      }
    ])
  }

  const removeStep = (index: number) => {
    const current = form.getValues('default_plan') || []
    form.setValue(
      'default_plan',
      current.filter((_, i) => i !== index)
    )
  }

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

      {/* Default Plan Table */}
      {enableMultiRun && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Default Plan</CardTitle>
          </CardHeader>
          <CardContent>

            <table className="w-full border text-sm">
              <thead className="bg-muted">
                <tr>
                  <th className="p-2 border">Step</th>
                  <th className="p-2 border">Status</th>
                  <th className="p-2 border">Instruction</th>
                  <th className="p-2 border">Output Ref</th>
                  <th className="p-2 border"></th>
                </tr>
              </thead>

              <tbody>
                {defaultPlan.map((step, index) => (
                  <tr key={index}>
                    <td className="border p-2">
                      <input
                        type="number"
                        value={step.step_index}
                        className="w-full border rounded px-2 py-1"
                        onChange={(e) => {
                          const updated = [...defaultPlan]
                          updated[index].step_index = Number(e.target.value)
                          form.setValue('default_plan', updated)
                        }}
                      />
                    </td>

                    <td className="border p-2">
                      <select
                        value={step.status}
                        className="w-full border rounded px-2 py-1"
                        onChange={(e) => {
                          const updated = [...defaultPlan]
                          updated[index].status = e.target.value as any
                          form.setValue('default_plan', updated)
                        }}
                      >
                        <option value="pending">pending</option>
                        <option value="in_progress">in_progress</option>
                        <option value="done">done</option>
                        <option value="failed">failed</option>
                      </select>
                    </td>

                    <td className="border p-2">
                      <input
                        value={step.instruction}
                        className="w-full border rounded px-2 py-1"
                        onChange={(e) => {
                          const updated = [...defaultPlan]
                          updated[index].instruction = e.target.value
                          form.setValue('default_plan', updated)
                        }}
                      />
                    </td>

                    <td className="border p-2">
                      <input
                        value={step.output_ref}
                        className="w-full border rounded px-2 py-1"
                        onChange={(e) => {
                          const updated = [...defaultPlan]
                          updated[index].output_ref = e.target.value
                          form.setValue('default_plan', updated)
                        }}
                      />
                    </td>

                    <td className="border p-2 text-center">
                      <button
                        type="button"
                        onClick={() => removeStep(index)}
                        className="text-red-500"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <button
              type="button"
              onClick={addStep}
              className="mt-4 rounded bg-primary px-4 py-2 text-white"
            >
              Add Step
            </button>

          </CardContent>
        </Card>
      )}
    </>
  )
}