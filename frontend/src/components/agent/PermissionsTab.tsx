import { useEffect, useMemo, useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { useNavigate, useLocation } from 'react-router-dom';
import { Plus } from 'lucide-react';

import type { AgentFormValues } from './types';
import type { ExecutionProfileOption, SSHConnectionOption } from './AdvancedTab';
import { parseOptionalNumber } from './AdvancedTab';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Combobox } from '@/components/ui/combobox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { MultiSelectCombobox, type MultiSelectComboboxOption } from '@/components/ui/multi-select-combobox';
import { ExperimentalBadge } from '@/components/common/ExperimentalBadge';
import { linkRoutes } from '@/lib/link-routes';
import { useDebounce } from '@/hooks/useDebounce';
import { searchUsers, searchRoles, fetchUsersByName, fetchRolesByName } from '@/services/agentApi';

interface NamedOption {
  name: string;
}

interface PermissionsTabProps {
  form: UseFormReturn<AgentFormValues>;
  owner?: string | null;
  executionProfileOptions?: ExecutionProfileOption[];
  loadingExecutionProfiles?: boolean;
  sshConnectionOptions?: SSHConnectionOption[];
  loadingSSHConnections?: boolean;
}

function mergeByName(base: NamedOption[], extra: NamedOption[]): NamedOption[] {
  const merged = [...base];
  const seen = new Set(base.map((item) => item.name));
  for (const item of extra) {
    if (!seen.has(item.name)) {
      merged.push(item);
      seen.add(item.name);
    }
  }
  return merged;
}

function approvalModeDescription(mode?: string): string {
  switch (mode) {
    case 'Auto Approve':
      return 'Code runs execute without manual approval.';
    case 'Ask Every Time':
      return 'This profile requires approval on every call.';
    case 'Never Allow':
      return 'This profile blocks all code execution calls.';
    default:
      return '';
  }
}

function buildOptions(items: NamedOption[]): MultiSelectComboboxOption[] {
  return items.map((item) => ({
    value: item.name,
    label: item.name,
  }));
}

export function PermissionsTab({
  form,
  owner,
  executionProfileOptions = [],
  loadingExecutionProfiles = false,
  sshConnectionOptions = [],
  loadingSSHConnections = false,
}: PermissionsTabProps) {
  const [userQuery, setUserQuery] = useState('');
  const [userOptionsData, setUserOptionsData] = useState<NamedOption[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [roleOptionsData, setRoleOptionsData] = useState<NamedOption[]>([]);
  const [rolesLoading, setRolesLoading] = useState(false);
  const debouncedUserQuery = useDebounce(userQuery, 250);

  const userOptions = useMemo(() => buildOptions(userOptionsData), [userOptionsData]);
  const roleOptions = useMemo(() => buildOptions(roleOptionsData), [roleOptionsData]);
  const selectedUsers = form.watch('allowed_users');
  const selectedRoles = form.watch('allowed_roles');
  const navigate = useNavigate();
  const location = useLocation();
  const enableConversationData = form.watch('enable_conversation_data');
  const selectedExecutionProfile = executionProfileOptions.find(
    (option) => option.value === form.watch('execution_profile'),
  );
  const executionProfileComboboxOptions = executionProfileOptions.map((option) => ({
    ...option,
    subtitle: option.approvalMode ? `Approval: ${option.approvalMode}` : undefined,
  }));
  const sshConnectionMultiSelectOptions = sshConnectionOptions.map((option) => ({
    value: option.value,
    label: option.label,
    description: option.description,
  }));
  const selectedApprovalHint = approvalModeDescription(selectedExecutionProfile?.approvalMode);

  // Lazy fetch on first render of this tab (Radix Tabs unmounts inactive
  // content by default, so this mount effect only fires once the Permissions
  // tab is actually opened). Seeds the pickers with a default page of
  // results plus the agent's currently-selected users/roles, so an admin
  // editing an existing restricted agent sees their picks as valid, labeled
  // options even if they fall outside the default/searched set.
  useEffect(() => {
    let cancelled = false;
    const currentUsers = form.getValues('allowed_users') || [];
    const currentRoles = form.getValues('allowed_roles') || [];

    setUsersLoading(true);
    Promise.all([searchUsers(''), fetchUsersByName(currentUsers)]).then(([defaults, selected]) => {
      if (cancelled) return;
      const resolvedNames = new Set(selected.map((u) => u.name));
      const unresolved = currentUsers.filter((name) => !resolvedNames.has(name)).map((name) => ({ name }));
      setUserOptionsData(mergeByName(mergeByName(defaults, selected), unresolved));
      setUsersLoading(false);
    });

    setRolesLoading(true);
    Promise.all([searchRoles(''), fetchRolesByName(currentRoles)]).then(([defaults, selected]) => {
      if (cancelled) return;
      const resolvedNames = new Set(selected.map((r) => r.name));
      const unresolved = currentRoles.filter((name) => !resolvedNames.has(name)).map((name) => ({ name }));
      setRoleOptionsData(mergeByName(mergeByName(defaults, selected), unresolved));
      setRolesLoading(false);
    });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Search-as-you-type for users; roles are eagerly fetched once above and
  // filtered client-side by MultiSelectCombobox's own default behavior.
  useEffect(() => {
    setUsersLoading(true);
    searchUsers(debouncedUserQuery).then((results) => {
      const currentUsers = form.getValues('allowed_users') || [];
      const selectedButMissing = userOptionsData.filter(
        (option) => currentUsers.includes(option.name) && !results.some((r) => r.name === option.name),
      );
      setUserOptionsData(mergeByName(results, selectedButMissing));
      setUsersLoading(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedUserQuery]);

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
              <FormItem className="flex flex-row items-center justify-between rounded-md border p-4">
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
                <FormLabel>Allowed users</FormLabel>
                <FormControl>
                  <MultiSelectCombobox
                    options={userOptions}
                    values={field.value || []}
                    onValuesChange={field.onChange}
                    placeholder={usersLoading ? 'Loading users...' : 'Select users'}
                    searchPlaceholder="Search users..."
                    emptyText="No users found."
                    searchValue={userQuery}
                    onSearchChange={setUserQuery}
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
                <FormLabel>Allowed roles</FormLabel>
                <FormControl>
                  <MultiSelectCombobox
                    options={roleOptions}
                    values={field.value || []}
                    onValuesChange={field.onChange}
                    placeholder={rolesLoading ? 'Loading roles...' : 'Select roles'}
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
            <div className="rounded-lg border border-dashed bg-paper-deep/30 p-4 text-sm text-steel">
              This agent is restricted to {selectedUsers?.length || 0} user(s) and {selectedRoles?.length || 0} role(s),
              in addition to the document owner.
            </div>
          ) : null}

          <div className="text-sm text-steel">
            {owner
              ? <>The agent&apos;s owner ({owner}) always retains access, regardless of the settings above.</>
              : <>The agent&apos;s owner always retains access, regardless of the settings above.</>}
          </div>
        </CardContent>
      </Card>

      {enableConversationData && (
        <Card>
          <CardHeader>
            <CardTitle>Conversation Data Access</CardTitle>
            <CardDescription>
              Control the API access level this agent has over stored conversation data.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6">
            <FormField
              control={form.control}
              name="conversation_data_api_permission"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Conversation Data API Permission</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value || ''}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="None" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="Read">Read</SelectItem>
                      <SelectItem value="Write">Write</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    Select API access level. &apos;Read&apos; allows reading only. &apos;Write&apos; allows reading and writing.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Code Execution</CardTitle>
          <CardDescription>
            Allow this agent to run Python code through the sandboxed Code Execution tool.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="allow_code_execution"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Allow Code Execution</FormLabel>
                  <FormDescription>
                    Explicit second confirmation enabling the Python Code Execution tool for this agent. The tool stays inert until this is checked and an Execution Profile is selected.
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />

          {form.watch('allow_code_execution') && (
            <>
              <FormField
                control={form.control}
                name="execution_profile"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Execution Profile</FormLabel>
                    <div className="flex items-center gap-2">
                      <FormControl>
                        <Combobox
                          options={executionProfileComboboxOptions}
                          value={field.value}
                          onValueChange={(v) => field.onChange(v || undefined)}
                          placeholder={loadingExecutionProfiles ? 'Loading profiles...' : 'Select an Execution Profile'}
                          disabled={loadingExecutionProfiles}
                          searchPlaceholder="Search execution profiles..."
                          emptyText="No enabled Execution Profiles found."
                          linkTo={linkRoutes.executionProfile}
                        />
                      </FormControl>
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => {
                          const returnTo = `${location.pathname}#permissions`;
                          const selectedField = 'execution_profile';
                          try {
                            localStorage.setItem(
                              'executionProfileCreateReturnTo',
                              JSON.stringify({ returnTo, selectedField }),
                            );
                          } catch {
                            // ignore storage failures
                          }
                          navigate('/execution-profiles/new', {
                            state: {
                              returnTo,
                              selectedField,
                              showTab: 'permissions',
                            },
                          });
                        }}
                      >
                        <Plus className="w-4 h-4 mr-2" />
                        New
                      </Button>
                    </div>
                    <FormDescription>
                      Caps modules, network, filesystem, broker capabilities, and resource limits for code runs. Execution Profiles are managed by admins in the Frappe desk.
                    </FormDescription>
                    {selectedExecutionProfile && selectedApprovalHint && (
                      <div className="flex flex-wrap items-center gap-2 pt-2">
                        {selectedExecutionProfile.approvalMode ? (
                          <Badge variant="outline">Approval: {selectedExecutionProfile.approvalMode}</Badge>
                        ) : null}
                        <span className="text-sm text-muted-foreground">{selectedApprovalHint}</span>
                      </div>
                    )}
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="execution_shared_dir_limit_mb"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Shared Dir Limit (MB)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        placeholder="Profile default"
                        {...field}
                        value={field.value?.toString() || ''}
                        onChange={(e) => field.onChange(parseOptionalNumber(e.target.value, (v) => parseInt(v, 10)))}
                      />
                    </FormControl>
                    <FormDescription>
                      Optional per-agent cap on the per-conversation shared directory. Must be at or below the selected profile&apos;s own limit (enforced server-side). Leave blank to use the profile default.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <div className="flex items-center gap-2.5">
              <span>SSH Execution</span>
              <ExperimentalBadge size="sm" />
            </div>
          </CardTitle>
          <CardDescription>
            Allow this agent to run one-shot SSH commands against explicitly allowlisted SSH Connection records. Interactive PTY sessions are deferred.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="allow_ssh"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4 sm:col-span-2">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Allow SSH Execution</FormLabel>
                  <FormDescription>
                    Enables the SSH execution tool for this agent only when at least one SSH Connection is selected below and the acting user holds the ssh.run capability.
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />

          {form.watch('allow_ssh') && (
            <>
              <FormField
                control={form.control}
                name="ssh_connections"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Allowlisted SSH Connections</FormLabel>
                    <div className="flex items-center gap-2">
                      <FormControl>
                        <MultiSelectCombobox
                          options={sshConnectionMultiSelectOptions}
                          values={field.value || []}
                          onValuesChange={field.onChange}
                          placeholder={loadingSSHConnections ? 'Loading SSH connections...' : 'Select SSH connections'}
                          searchPlaceholder="Search SSH connections..."
                          emptyText="No enabled SSH connections found."
                          disabled={loadingSSHConnections}
                        />
                      </FormControl>
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => {
                          const returnTo = `${location.pathname}#permissions`;
                          const selectedField = 'ssh_connections';
                          try {
                            localStorage.setItem(
                              'sshConnectionCreateReturnTo',
                              JSON.stringify({ returnTo, selectedField }),
                            );
                          } catch {
                            // ignore storage failures
                          }
                          navigate('/ssh-connections/new', {
                            state: {
                              returnTo,
                              selectedField,
                              showTab: 'permissions',
                            },
                          });
                        }}
                      >
                        <Plus className="w-4 h-4 mr-2" />
                        New
                      </Button>
                    </div>
                    <FormDescription>
                      Each command call must pick one of these connections. Use the Frappe desk SSH Connection DocType to store credentials, enroll host keys, and rotate secrets.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="sm:col-span-2 rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                SSH uses the selected Execution Profile only when present, for approval mode and network policy. Without a profile, the backend falls back to strict default timeouts and Ask Every Time approval.
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
