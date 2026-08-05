import { UseFormReturn } from 'react-hook-form';
import {
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormMessage,
} from '@/components/ui/form';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Combobox, type ComboboxOption } from '@/components/ui/combobox';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { linkRoutes } from '@/lib/link-routes';
import { SwitchField } from '../SwitchField';
import {
  memoryCaptureModes,
  memoryDefaultStatuses,
  type MemoryPolicyFormValues,
} from '../memoryPolicyFormSchema';

interface CaptureTabProps {
  form: UseFormReturn<MemoryPolicyFormValues>;
  agentOptions: ComboboxOption[];
}

export function CaptureTab({ form, agentOptions }: CaptureTabProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Capture</CardTitle>
        <CardDescription>Control how new memory records are created and approved.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        <FormField
          control={form.control}
          name="capture_mode"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Capture Mode</FormLabel>
              <Select value={field.value} onValueChange={field.onChange}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {memoryCaptureModes.map((mode) => (
                    <SelectItem key={mode} value={mode}>
                      {mode}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>
                <span className="block"><strong>Manual</strong> — only explicit user or tool-call writes create memory.</span>
                <span className="block"><strong>Agent Suggested</strong> — a background job proposes memory records after each run; they always land as Draft for approval.</span>
                <span className="block"><strong>Automatic</strong> — same background extraction, but records follow this policy's normal Approval Required / Default Status handling.</span>
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="learning_agent"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Learning Agent</FormLabel>
              <FormControl>
                <Combobox
                  options={agentOptions}
                  value={field.value}
                  onValueChange={(v) => field.onChange(v || undefined)}
                  placeholder="Use the conversation's agent"
                  searchPlaceholder="Search agents..."
                  emptyText="No agents found."
                  linkTo={linkRoutes.agent}
                />
              </FormControl>
              <FormDescription>
                Optional dedicated agent that runs background memory extraction (used when
                Capture Mode is Agent Suggested or Automatic), instead of the conversation's own
                agent. Lets extraction run on a cheap model without touching the main agent's
                context or budget.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <SwitchField
          form={form}
          name="approval_required"
          label="Approval required"
          description="New memory records start as pending and must be approved by a user before becoming active. Turn this off to trust captured memory automatically."
        />

        <FormField
          control={form.control}
          name="default_status"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Default Status</FormLabel>
              <Select value={field.value} onValueChange={field.onChange}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {memoryDefaultStatuses.map((status) => (
                    <SelectItem key={status} value={status}>
                      {status}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>
                Status assigned to newly captured memory records before any approval step runs.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="allowed_record_types"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Allowed Record Types</FormLabel>
              <FormControl>
                <Textarea
                  placeholder={'One record type per line, e.g.\nfact\npreference\ninstruction'}
                  className="min-h-[80px] resize-y font-mono text-sm"
                  {...field}
                />
              </FormControl>
              <FormDescription>
                Optional newline-separated list of record types this policy may capture. Leave
                empty to allow all types.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </CardContent>
    </Card>
  );
}
