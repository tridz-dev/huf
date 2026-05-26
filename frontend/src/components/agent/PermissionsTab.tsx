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
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <FormField
            control={form.control}
            name="allow_guest"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Allow Guest API Access</FormLabel>
                  <FormDescription>
                    When enabled, Guest users can run this agent through whitelisted API endpoints.
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
                  Leave empty to avoid user-specific restrictions. Add specific users for targeted access.
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
                  Use roles for scalable access control across teams without listing every user individually.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          {(selectedUsers?.length || selectedRoles?.length) ? (
            <div className="rounded-lg border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
              This agent is restricted to {selectedUsers?.length || 0} user(s) and {selectedRoles?.length || 0} role(s),
              in addition to the document owner.
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
