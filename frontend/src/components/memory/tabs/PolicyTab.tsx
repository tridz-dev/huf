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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Combobox, type ComboboxOption } from '@/components/ui/combobox';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { linkRoutes } from '@/lib/link-routes';
import { SwitchField } from '../SwitchField';
import { memoryScopeTypes, type MemoryPolicyFormValues } from '../memoryPolicyFormSchema';

interface PolicyTabProps {
  form: UseFormReturn<MemoryPolicyFormValues>;
  isNew: boolean;
  agentOptions: ComboboxOption[];
}

export function PolicyTab({ form, isNew, agentOptions }: PolicyTabProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Policy</CardTitle>
        <CardDescription>
          Identify this policy and choose which agent (if any) it is dedicated to.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        {isNew && (
          <FormField
            control={form.control}
            name="policy_name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Policy name</FormLabel>
                <FormControl>
                  <Input placeholder="e.g. support-agent-memory" {...field} />
                </FormControl>
                <FormDescription>Unique identifier for this memory policy.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Description</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="What this policy is for and what it does, e.g. 'Support agent memory — remembers customer preferences across tickets, requires approval before use.'"
                  className="min-h-[80px] resize-y"
                  {...field}
                />
              </FormControl>
              <FormDescription>
                Shown to whoever is choosing a policy for an agent — explain the intent, not just
                repeat the settings below.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <SwitchField
          form={form}
          name="enabled"
          label="Enabled"
          description="Only enabled policies are selectable from an agent's Memory settings and are evaluated at runtime."
        />

        <div className="grid gap-6 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="agent"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Agent</FormLabel>
                <FormControl>
                  <Combobox
                    options={agentOptions}
                    value={field.value}
                    onValueChange={(v) => field.onChange(v || undefined)}
                    placeholder="Any agent"
                    searchPlaceholder="Search agents..."
                    emptyText="No agents found."
                    linkTo={linkRoutes.agent}
                  />
                </FormControl>
                <FormDescription>
                  Optional. Restricts this policy to a single agent instead of being reusable
                  across any agent that selects it.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="scope_type"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Scope type</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {memoryScopeTypes.map((scope) => (
                      <SelectItem key={scope} value={scope}>
                        {scope}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>
                  Determines which "bucket" memory records are grouped under: a single
                  conversation, a user, a role, an agent, a workspace, a site, or globally.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="scope_key"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Scope key</FormLabel>
              <FormControl>
                <Input placeholder="Leave empty to use runtime context" {...field} />
              </FormControl>
              <FormDescription>
                Optional fixed scope key. If empty, the runtime context (current user, agent, or
                site) decides the key at conversation time.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </CardContent>
    </Card>
  );
}
