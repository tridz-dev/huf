/**
 * AccessTab: who can use it, public access, code execution, SSH, desktop access.
 * Controlled by the page's react-hook-form (AgentFormValues).
 *
 * Field mapping (constraints.md (a)+(b), Permissions tab):
 *   allow_all_users ........... "Who can use it" ToggleRow ("everyone signed in"; applies only when users+roles empty)
 *   allowed_users, allowed_roles .. "Who can use it" chip pickers (MultiSelectCombobox; options via props / useAccessPrincipals)
 *   allow_guest ............... Public access ToggleReveal
 *   conversation_data_api_permission .. FormSection, shown only when enable_conversation_data (set in Advanced)
 *   allow_code_execution ...... Code execution ToggleReveal -> execution_profile, execution_shared_dir_limit_mb
 *   allow_ssh ................. SSH ToggleReveal -> ssh_connections
 *   desktop_access_cli/files/skills/local_mcp/browser/installs/processes, allow_remote_desktop
 *                              Desktop access ToggleReveal. Persisted by the page's separate db.updateDoc path:
 *                              `onDesktopAccessChange` / `onRemoteDesktopChange` fire in addition to updating the form.
 * Master switch semantics: ON when any of the seven is not "off" or remote control is on. Turning it OFF sets all seven to
 * "off" (remote control untouched but hidden); turning it ON sets all seven to "ask" (the safe middle). Per-capability
 * values are then adjustable.
 * Owner always retains access (note rendered from `owner`).
 */
import type { ReactNode } from 'react';
import { Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
import { Field } from '@/components/ui/field';
import { MultiSelectCombobox, type MultiSelectComboboxOption } from '@/components/ui/multi-select-combobox';
import { ExperimentalBadge } from '@/components/common/ExperimentalBadge';
import { linkRoutes } from '@/lib/link-routes';
import { FormSection, ToggleReveal, ToggleRow } from '@/components/builder';
import { StatusSentence } from '@/components/patterns';
import { DESKTOP_ACCESS_FIELDS, toDesktopAccessLevel, type DesktopAccessFieldName, type DesktopAccessLevel } from '../types';
import type { ExecutionProfileOption, SSHConnectionOption } from '../AdvancedTab';
import { NumberField, SelectField, useFormBinding, type AgentForm } from './fields';

export interface AccessTabProps {
  form: AgentForm;
  owner?: string | null;
  userOptions?: MultiSelectComboboxOption[];
  roleOptions?: MultiSelectComboboxOption[];
  usersLoading?: boolean;
  rolesLoading?: boolean;
  onUserSearch?: (query: string) => void;
  userQuery?: string;
  executionProfileOptions?: ExecutionProfileOption[];
  loadingExecutionProfiles?: boolean;
  sshConnectionOptions?: SSHConnectionOption[];
  loadingSSHConnections?: boolean;
  /** Page navigates to create an execution profile / SSH connection. */
  onCreateExecutionProfile?: () => void;
  onCreateSSHConnection?: () => void;
  /** Desktop access loads separately; controls stay disabled until 'ready'. */
  desktopAccessStatus?: 'loading' | 'ready' | 'error';
  /** Fired with each desktop-access change so the page can save via its separate db.updateDoc path. */
  onDesktopAccessChange?: (field: DesktopAccessFieldName, level: DesktopAccessLevel) => void;
  onRemoteDesktopChange?: (allowed: boolean) => void;
  locked?: boolean;
}

const LEVELS: { value: DesktopAccessLevel; label: string }[] = [
  { value: 'off', label: 'Off' }, { value: 'ask', label: 'Ask' }, { value: 'allowed', label: 'Allowed' },
];

const APPROVAL_HINT: Record<string, string> = {
  'Auto Approve': 'Code runs execute without manual approval.',
  'Ask Every Time': 'This profile requires approval on every call.',
  'Never Allow': 'This profile blocks all code execution calls.',
};

export function AccessTab({
  form, owner, userOptions = [], roleOptions = [], usersLoading = false, rolesLoading = false, onUserSearch, userQuery,
  executionProfileOptions = [], loadingExecutionProfiles = false, sshConnectionOptions = [], loadingSSHConnections = false,
  onCreateExecutionProfile, onCreateSSHConnection, desktopAccessStatus = 'ready', onDesktopAccessChange, onRemoteDesktopChange, locked = false,
}: AccessTabProps) {
  const { get, set, error } = useFormBinding(form);
  const users = get('allowed_users') ?? [];
  const roles = get('allowed_roles') ?? [];
  const restricted = users.length + roles.length > 0;
  const allowAll = Boolean(get('allow_all_users'));
  const profile = executionProfileOptions.find((o) => o.value === get('execution_profile'));
  const desktopLevels = DESKTOP_ACCESS_FIELDS.map((f) => toDesktopAccessLevel(get(f.name)));
  const remote = Boolean(get('allow_remote_desktop'));
  const desktopOn = desktopLevels.some((l) => l !== 'off') || remote;
  const desktopDisabled = desktopAccessStatus !== 'ready' || locked;

  const setLevel = (name: DesktopAccessFieldName, level: DesktopAccessLevel) => {
    set(name, level);
    onDesktopAccessChange?.(name, level);
  };

  const who: ReactNode = restricted
    ? <StatusSentence tone="ready">Only {users.length} user(s) and {roles.length} role(s)</StatusSentence>
    : allowAll
      ? <StatusSentence tone="ready">Everyone signed in</StatusSentence>
      : <StatusSentence tone="neutral">Only the owner</StatusSentence>;

  return (
    <div className="space-y-6">
      <FormSection title="Who can use it" description="The owner always has access.">
        <div data-testid="who-status">{who}</div>
        <div className="rounded-lg border border-line">
          <ToggleRow title="Everyone who is signed in" checked={allowAll} disabled={locked}
            description="Applies only while no users or roles are listed below. Off: only the owner can run it."
            onCheckedChange={(v) => set('allow_all_users', v)} />
        </div>
        <Field label="Specific people" hint="When anyone is listed, only they (and the owner) can run it.">
          {() => (
            <MultiSelectCombobox options={userOptions} values={users} onValuesChange={(v) => set('allowed_users', v)} disabled={locked}
              placeholder={usersLoading ? 'Loading users...' : 'Add people'} searchPlaceholder="Search users..." emptyText="No users found."
              searchValue={userQuery} onSearchChange={onUserSearch} />
          )}
        </Field>
        <Field label="Roles" hint="Everyone holding one of these roles, for example a team.">
          {() => (
            <MultiSelectCombobox options={roleOptions} values={roles} onValuesChange={(v) => set('allowed_roles', v)} disabled={locked}
              placeholder={rolesLoading ? 'Loading roles...' : 'Add roles'} searchPlaceholder="Search roles..." emptyText="No roles found." />
          )}
        </Field>
        <p className="text-micro text-steel">
          {owner ? `The owner (${owner}) always has access.` : 'The owner always has access.'}
        </p>
      </FormSection>

      <FormSection title="Public access" description="Let people use it without signing in.">
        <ToggleReveal label="Anyone with the link, no login" checked={Boolean(get('allow_guest'))} onCheckedChange={(v) => set('allow_guest', v)} disabled={locked}
          description="Not just your organization. Users and roles are not checked for guests. Use for public-facing agents such as a support widget; if unsure, leave off."
          status={<StatusSentence tone="attention">Public</StatusSentence>} />
      </FormSection>

      {get('enable_conversation_data') && (
        <FormSection title="Conversation data" description="API access level over stored conversation data.">
          <SelectField label="Conversation data API permission" value={get('conversation_data_api_permission')} onChange={(v) => set('conversation_data_api_permission', v)}
            placeholder="None" hint="Read allows reading only. Write allows reading and writing." error={error('conversation_data_api_permission')}
            options={[{ value: 'Read', label: 'Read' }, { value: 'Write', label: 'Write' }]} />
        </FormSection>
      )}

      <FormSection title="Code and remote access" description="Powerful tools. Turn on only what this agent needs.">
        <ToggleReveal label="Run code" checked={Boolean(get('allow_code_execution'))} onCheckedChange={(v) => set('allow_code_execution', v)} disabled={locked}
          description="Lets it run Python in a sandbox. Inert until an execution profile is chosen."
          status={profile ? <StatusSentence tone="ready">{profile.label}</StatusSentence> : <StatusSentence tone="attention">Choose a profile</StatusSentence>}>
          <Field label="Execution profile" hint="Caps modules, network, files and resources for code runs. Managed by admins in the Frappe desk.">
            {(p) => (
              <div className="flex items-center gap-2">
                <Combobox id={p.id} options={executionProfileOptions.map((o) => ({ ...o, subtitle: o.approvalMode ? `Approval: ${o.approvalMode}` : undefined }))}
                  value={get('execution_profile')} onValueChange={(v) => set('execution_profile', v || undefined)} disabled={loadingExecutionProfiles}
                  placeholder={loadingExecutionProfiles ? 'Loading profiles...' : 'Select an execution profile'} searchPlaceholder="Search execution profiles..."
                  emptyText="No enabled execution profiles found." linkTo={linkRoutes.executionProfile} />
                {onCreateExecutionProfile && <Button type="button" variant="secondary" onClick={onCreateExecutionProfile}><Plus className="mr-2 h-4 w-4" />New</Button>}
              </div>
            )}
          </Field>
          {profile?.approvalMode && (
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">Approval: {profile.approvalMode}</Badge>
              <span className="text-micro text-steel">{APPROVAL_HINT[profile.approvalMode] ?? ''}</span>
            </div>
          )}
          <NumberField label="Shared folder limit (MB)" placeholder="Profile default" value={get('execution_shared_dir_limit_mb')}
            onChange={(v) => set('execution_shared_dir_limit_mb', v)} error={error('execution_shared_dir_limit_mb')}
            hint="Optional cap per conversation. At or below the profile's own limit. Blank uses the profile default." />
        </ToggleReveal>

        <ToggleReveal label={<span className="flex items-center gap-2">Run commands over SSH <ExperimentalBadge size="sm" /></span>}
          checked={Boolean(get('allow_ssh'))} onCheckedChange={(v) => set('allow_ssh', v)} disabled={locked}
          description="One-shot commands on SSH connections you allowlist. Needs the ssh.run capability.">
          <Field label="Allowed SSH connections" hint="Each command must use one of these. Credentials are stored on the SSH Connection record." error={error('ssh_connections')}>
            {() => (
              <div className="flex items-center gap-2">
                <MultiSelectCombobox options={sshConnectionOptions.map((o) => ({ value: o.value, label: o.label, description: o.description }))}
                  values={get('ssh_connections') ?? []} onValuesChange={(v) => set('ssh_connections', v)} disabled={loadingSSHConnections}
                  placeholder={loadingSSHConnections ? 'Loading SSH connections...' : 'Select SSH connections'} searchPlaceholder="Search SSH connections..."
                  emptyText="No enabled SSH connections found." />
                {onCreateSSHConnection && <Button type="button" variant="secondary" onClick={onCreateSSHConnection}><Plus className="mr-2 h-4 w-4" />New</Button>}
              </div>
            )}
          </Field>
          <p className="text-micro text-steel">Uses the selected execution profile for approval and network policy when set; otherwise strict timeouts and Ask Every Time.</p>
        </ToggleReveal>

        <div data-testid="desktop-access-card">
          <ToggleReveal label="Use Huf Desktop" checked={desktopOn} disabled={desktopDisabled}
            description="What it may do on a computer running Huf Desktop. Each setting is a ceiling; the person at the desktop can restrict it further."
            onCheckedChange={(on) => {
              for (const f of DESKTOP_ACCESS_FIELDS) setLevel(f.name, on ? 'ask' : 'off');
            }}>
            {desktopAccessStatus === 'error' && <p role="alert" className="text-micro text-destructive">Desktop access settings could not be loaded. Reload the page to edit them.</p>}
            {desktopAccessStatus === 'loading' && <p className="text-micro text-steel">Loading desktop access...</p>}
            <div className="grid gap-4 sm:grid-cols-2">
              {DESKTOP_ACCESS_FIELDS.map(({ name, label }) => (
                <SelectField key={name} label={label} value={toDesktopAccessLevel(get(name))} disabled={desktopDisabled}
                  onChange={(v) => setLevel(name, v as DesktopAccessLevel)} options={LEVELS} />
              ))}
            </div>
            <ToggleRow title="Allow remote desktop control" checked={remote} disabled={desktopDisabled}
              description="Runs started from the web or mobile app by the same user may use this agent's tools on a desktop with remote control on. Both must be on."
              onCheckedChange={(v) => { set('allow_remote_desktop', v); onRemoteDesktopChange?.(v); }} />
          </ToggleReveal>
        </div>
      </FormSection>
    </div>
  );
}
