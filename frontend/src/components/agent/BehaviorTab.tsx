import {
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription
} from '@/components/ui/form'

import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell
} from "@/components/ui/table"

import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem
} from "@/components/ui/select"

import { Switch } from '@/components/ui/switch'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { UseFormReturn } from 'react-hook-form'
import type { AgentFormValues } from './types'
import { toast } from 'sonner'

interface BehaviorTabProps {
  form: UseFormReturn<AgentFormValues>;
}

export function BehaviorTab({ form }: BehaviorTabProps) {
  const persistConversationEnabled = form.watch('persist_conversation');
  const enableMultiRun = form.watch('enable_multi_run');

  const defaultPlan = form.watch('default_plan') || []

  // Ensure at least one row exists
  if (enableMultiRun && defaultPlan.length === 0) {
    form.setValue('default_plan', [
      {
        step_index: 1,
        status: 'pending',
        instruction: '',
        output_ref: ''
      }
    ])
  }

  const updateRow = (index: number, field: string, value: any) => {

    const current = form.getValues('default_plan') || []
    const updated = [...current]

    updated[index] = {
      ...updated[index],
      [field]: value
    }

    const isLastRow = index === updated.length - 1

    const hasValue =
      updated[index].instruction ||
      updated[index].output_ref ||
      updated[index].status !== 'pending'

    if (isLastRow && hasValue) {
      updated.push({
        step_index: updated.length + 1,
        status: 'pending',
        instruction: '',
        output_ref: ''
      })
    }

    const normalized = updated.map((row, i) => ({
      ...row,
      step_index: i + 1
    }))

    form.setValue('default_plan', normalized)
  }
  const removeStep = (index: number) => {
    const current = form.getValues('default_plan') || []

    if (current.length === 1) return

    const filtered = current.filter((_, i) => i !== index)

    const normalized = filtered.map((row, i) => ({
      ...row,
      step_index: i + 1
    }))

    form.setValue('default_plan', normalized)
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
                    When checked, Doc Event and Scheduled runs create conversation history per initiating user.
                  </FormDescription>
                </div>
                <FormControl className="ml-1">
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

                        const chatEnabled = form.getValues('allow_chat')

                        if (chatEnabled) {
                          form.setValue('allow_chat', false, { shouldDirty: true })
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


      {enableMultiRun && (
        <Card className="mt-6">

          <CardHeader>
            <CardTitle>Default Plan</CardTitle>
          </CardHeader>

          <CardContent>

            <Table className="border">

              <TableHeader className="bg-muted">
                <TableRow>
                  <TableHead>Step</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Instruction</TableHead>
                  <TableHead>Output Ref</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>

              <TableBody>

                {defaultPlan.map((step, index) => (

                  <TableRow key={index}>

                    <TableCell className="font-medium">
                      {index + 1}
                    </TableCell>

                    <TableCell>
                      <Select
                        value={step.status}
                        onValueChange={(value) => updateRow(index, "status", value)}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select status" />
                        </SelectTrigger>

                        <SelectContent>
                          <SelectItem value="pending">Pending</SelectItem>
                          <SelectItem value="in_progress">In Progress</SelectItem>
                          <SelectItem value="done">Done</SelectItem>
                          <SelectItem value="failed">Failed</SelectItem>
                        </SelectContent>
                      </Select>
                    </TableCell>

                    <TableCell>
                      <Input
                        value={step.instruction}
                        onChange={(e) =>
                          updateRow(index, "instruction", e.target.value)
                        }
                      />
                    </TableCell>

                    <TableCell>
                      <Input
                        value={step.output_ref}
                        onChange={(e) =>
                          updateRow(index, "output_ref", e.target.value)
                        }
                      />
                    </TableCell>

                    <TableCell className="text-center">
                      <Button
                        type="button"
                        variant="destructive"
                        size="sm"
                        onClick={() => removeStep(index)}
                      >
                        Remove
                      </Button>
                    </TableCell>

                  </TableRow>

                ))}

              </TableBody>

            </Table>

          </CardContent>

        </Card>
      )}
    </>
  )
}