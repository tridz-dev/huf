import { UseFormReturn } from 'react-hook-form';
import {
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormMessage,
} from '@/components/ui/form';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Combobox, type ComboboxOption } from '@/components/ui/combobox';
import { MultiSelectCombobox } from '@/components/ui/multi-select-combobox';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { linkRoutes } from '@/lib/link-routes';
import { SwitchField } from '../SwitchField';
import {
  memoryCaptureModes,
  memoryDefaultStatuses,
  memoryRecordTypes,
  type MemoryPolicyFormValues,
} from '../memoryPolicyFormSchema';

const recordTypeOptions = memoryRecordTypes.map((type) => ({ value: type, label: type }));

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
              <FormLabel>Capture mode</FormLabel>
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
                <span className="block"><strong>Automatic</strong> — same background extraction, but records follow this policy's Approval Required / Default Status handling below.</span>
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
              <FormLabel>Learning agent</FormLabel>
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
          description="New memory records are forced to Draft status regardless of Default Status below, and must be approved by a user before becoming active. Turn this off to trust captured memory automatically."
        />

        <FormField
          control={form.control}
          name="default_status"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Default status</FormLabel>
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
                Status assigned to newly captured records when Approval Required is off. Ignored
                (records are always Draft) while Approval Required is checked.
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
              <FormLabel>Allowed record types</FormLabel>
              <FormControl>
                <MultiSelectCombobox
                  options={recordTypeOptions}
                  values={field.value}
                  onValuesChange={field.onChange}
                  placeholder="All record types allowed"
                  searchPlaceholder="Search record types..."
                  emptyText="No record types found."
                />
              </FormControl>
              <FormDescription>
                <span className="block">
                  Which of Memory Record&apos;s Record Type values this policy may capture.
                  Pick from the list — it&apos;s the same set the backend enforces, so nothing
                  selected here can ever fail with a &quot;not allowed by policy&quot; error.
                </span>
                <span className="block">Leave empty to allow all record types.</span>
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </CardContent>
    </Card>
  );
}
