import { UseFormReturn } from 'react-hook-form';
import {
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Combobox, type ComboboxOption } from '@/components/ui/combobox';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { linkRoutes } from '@/lib/link-routes';
import { SwitchField } from '../SwitchField';
import type { MemoryPolicyFormValues } from '../memoryPolicyFormSchema';

interface GuardrailsTabProps {
  form: UseFormReturn<MemoryPolicyFormValues>;
  knowledgeSourceOptions: ComboboxOption[];
}

export function GuardrailsTab({ form, knowledgeSourceOptions }: GuardrailsTabProps) {
  const watchAutoPromote = form.watch('auto_promote_to_knowledge');

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Write permissions</CardTitle>
          <CardDescription>
            Control which scopes this policy is allowed to write memory records into.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <SwitchField
            form={form}
            name="allow_agent_write"
            label="Allow agent write"
            description="Lets the agent itself write memory records (via a tool call), not just users. If off, every write attempt under this policy is blocked, regardless of the scope toggles below."
          />
          <SwitchField
            form={form}
            name="allow_user_scope_write"
            label="Allow user scope write"
            description="Permits writing memory records scoped to the current user."
          />
          <SwitchField
            form={form}
            name="allow_role_scope_write"
            label="Allow role scope write"
            description="Permits writing memory records scoped to a role, shared across all users with it."
          />
          <SwitchField
            form={form}
            name="allow_agent_scope_write"
            label="Allow agent scope write"
            description="Permits writing memory records scoped to the agent, shared across all its conversations."
          />
          <SwitchField
            form={form}
            name="allow_site_scope_write"
            label="Allow site scope write"
            description="Permits writing memory records scoped globally to this site. Use sparingly."
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Knowledge projection</CardTitle>
          <CardDescription>
            Optionally promote high-confidence memories into a permanent Knowledge Source.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <SwitchField
            form={form}
            name="auto_promote_to_knowledge"
            label="Auto promote to knowledge"
            description="Automatically copies memory records that meet or exceed both Min Confidence and Min Importance below into a Knowledge Source, making them retrievable outside the memory system."
          />

          {watchAutoPromote && (
            <>
              <FormField
                control={form.control}
                name="knowledge_source"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Knowledge source</FormLabel>
                    <FormControl>
                      <Combobox
                        options={knowledgeSourceOptions}
                        value={field.value}
                        onValueChange={(v) => field.onChange(v || undefined)}
                        placeholder="Select a knowledge source"
                        searchPlaceholder="Search knowledge sources..."
                        emptyText="No knowledge sources found."
                        linkTo={linkRoutes.knowledgeSource}
                      />
                    </FormControl>
                    <FormDescription>
                      Required when Auto Promote is enabled. The Knowledge Source that promoted
                      memories are written into.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="grid gap-6 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="promotion_min_confidence"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Min confidence</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={0}
                          max={1}
                          step={0.05}
                          {...field}
                          onChange={(e) => field.onChange(Number(e.target.value))}
                        />
                      </FormControl>
                      <FormDescription>
                        Minimum confidence score (0-1) a memory record must have to be promoted.
                        A record is promoted only when it meets or exceeds both this and Min
                        Importance.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="promotion_min_importance"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Min importance</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={0}
                          max={1}
                          step={0.05}
                          {...field}
                          onChange={(e) => field.onChange(Number(e.target.value))}
                        />
                      </FormControl>
                      <FormDescription>
                        Minimum importance score (0-1) a memory record must have to be promoted.
                        A record is promoted only when it meets or exceeds both this and Min
                        Confidence.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Lifecycle</CardTitle>
          <CardDescription>Control how long memory records live under this policy.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <FormField
            control={form.control}
            name="ttl_days"
            render={({ field }) => (
              <FormItem>
                <FormLabel>TTL days</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    min={0}
                    {...field}
                    onChange={(e) => field.onChange(Number(e.target.value))}
                  />
                </FormControl>
                <FormDescription>
                  Number of days before a memory record expires and is archived. 0 means memory
                  never expires automatically.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="metadata_json"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Metadata JSON</FormLabel>
                <FormControl>
                  <Textarea
                    placeholder="{}"
                    className="min-h-[100px] resize-y font-mono text-sm"
                    {...field}
                  />
                </FormControl>
                <FormDescription>
                  Optional free-form JSON for policy-specific settings not covered above, consumed
                  by custom tooling or automations.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </CardContent>
      </Card>
    </div>
  );
}
