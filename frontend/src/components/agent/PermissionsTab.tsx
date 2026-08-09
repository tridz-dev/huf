import { useMemo } from 'react';
import type { UseFormReturn } from 'react-hook-form';

import type { AgentFormValues } from './types';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Switch } from '@/components/ui/switch';
import { MultiSelectCombobox, type MultiSelectComboboxOption } from '@/components/ui/multi-select-combobox';

interface NamedOption {
  name: string;
}

interface PermissionsTabProps {
  form: UseFormReturn<AgentFormValues>;
  users: NamedOption[];
  roles: NamedOption[];
}

function buildOptions(items: NamedOption[]): MultiSelectComboboxOption[] {
  return items.map((item) => ({
    value: item.name,
    label: item.name,
  }));
}

export function PermissionsTab({ form, users, roles }: PermissionsTabProps) {
  const userOptions = useMemo(() => buildOptions(users), [users]);
  const roleOptions = useMemo(() => buildOptions(roles), [roles]);
  const selectedUsers = form.watch('allowed_users');
  const selectedRoles = form.watch('allowed_roles');

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Access Control</CardTitle>
          <CardDescription>
            Configure who can run this agent. If both lists are empty, any authenticated user can access it.
            Otherwise access is limited to the owner, selected users, or users with selected roles.
            <br />
            Agents reached via external channels (Slack, Discord, Teams, Telegram, voice) are only
            reachable if Allow Public / Unauthenticated Access is enabled below -- Allowed Users and
            Allowed Roles cannot be evaluated for those channels since external callers are not mapped
            to a HUF user.
            <br />
            This tab controls who can run this agent; it is separate from data-table agent access,
            which controls what an agent can do to a table.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <FormField
            control={form.control}
            name="allow_guest"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-none border p-4">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Allow Public / Unauthenticated Access</FormLabel>
                  <FormDescription>
                    If checked, anyone who can reach the API can run this agent without logging in -- not
                    just people in your organization. Guest access is governed by this switch alone;
                    Allowed Users and Allowed Roles are not evaluated for unauthenticated callers. Use only
                    for agents meant to be public-facing, such as an embedded support-chat widget. If
                    unsure, leave this off.
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="allowed_users"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Allowed Users</FormLabel>
                <FormControl>
                  <MultiSelectCombobox
                    options={userOptions}
                    values={field.value || []}
                    onValuesChange={field.onChange}
                    placeholder="Select users"
                    searchPlaceholder="Search users..."
                    emptyText="No users found."
                  />
                </FormControl>
                <FormDescription>
                  Add specific users to limit who can run this agent. If both Allowed Users and Allowed
                  Roles are left empty, every logged-in HUF user can run this agent -- leaving both empty
                  does not restrict access, it removes all restrictions.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="allowed_roles"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Allowed Roles</FormLabel>
                <FormControl>
                  <MultiSelectCombobox
                    options={roleOptions}
                    values={field.value || []}
                    onValuesChange={field.onChange}
                    placeholder="Select roles"
                    searchPlaceholder="Search roles..."
                    emptyText="No roles found."
                  />
                </FormControl>
                <FormDescription>
                  Use roles for scalable access control across teams without listing every user
                  individually -- e.g. restrict an HR agent to the HR Manager role. If both Allowed Users
                  and Allowed Roles are empty, every logged-in user can run this agent.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          {(selectedUsers?.length || selectedRoles?.length) ? (
            <div className="rounded-none border border-dashed bg-paper-deep/30 p-4 text-sm text-steel">
              This agent is restricted to {selectedUsers?.length || 0} user(s) and {selectedRoles?.length || 0} role(s),
              in addition to the document owner.
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
