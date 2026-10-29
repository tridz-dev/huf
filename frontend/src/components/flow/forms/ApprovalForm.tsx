import { useEffect, useState } from 'react';
import { APPROVER_TYPE_HELP } from '@/lib/flow/flowHelp';
import { Combobox } from '../../ui/combobox';
import { FieldHint } from '../FieldHint';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { getApproverRoles } from '../../../services/flowApi';
import { type ActionFormProps, BranchRows, type Opt, PickerTextarea, Section, str } from './formKit';

export function ApprovalForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const [roles, setRoles] = useState<Array<Opt & { subtitle?: string }>>([]);

  useEffect(() => {
    getApproverRoles()
      .then((l) => setRoles((l || []).map((r) => ({ value: r.name, label: r.name, subtitle: r.name === 'System Manager' ? 'Administrator-level role' : r.group === 'Huf' ? 'Huf role' : undefined }))))
      .catch(() => setRoles([]));
  }, []);
  const approverType = str(cfg.approver_type);
  const users = Array.isArray(cfg.approver_users) ? (cfg.approver_users as string[]) : [];
  return (
    <Section title={title} hint="Pauses the flow until someone approves or rejects. Approved and Rejected are separate paths. Approvers see the request in the bell menu at the top and on the run's details.">
      <div>
        <PickerTextarea
          id="approval-message"
          testId={f('message')}
          pickerTestId={`${f('message')}-picker`}
          nodeId={nodeId}
          label="Message for the approver"
          value={str(cfg.message)}
          onChange={(v) => patch({ message: v })}
          format={(ref) => `{${ref}}`}
          className="min-h-[60px]"
          placeholder="Approve this refund?"
        />
        <FieldHint testId="flow-hint-approval-message">What the approver reads. Say what is being approved and include the key facts with Insert data.</FieldHint>
        <Err field="message" />
      </div>
      <div>
        <Label htmlFor="approver-type" size="sm">Who can approve</Label>
        <Select
          value={approverType}
          onValueChange={(v) =>
            patch(
              v === 'role' ? { approver_type: 'role', approver_users: undefined }
                : v === 'user' ? { approver_type: 'user', approver_role: undefined }
                  : { approver_type: undefined, approver_role: undefined, approver_users: undefined }
            )
          }
        >
          <SelectTrigger id="approver-type" data-testid={f('approver_type')}>
            <SelectValue placeholder="Choose who can approve" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="role" data-testid="flow-option-approver-role">People with a role</SelectItem>
            <SelectItem value="user" data-testid="flow-option-approver-user">Specific people</SelectItem>
          </SelectContent>
        </Select>
        <FieldHint testId="flow-hint-approver-type">{APPROVER_TYPE_HELP[approverType] ?? 'Pick a role (everyone who has it can answer) or list specific people.'}</FieldHint>
        <Err field="approver_type" />
      </div>
      {approverType === 'role' && (
        <div>
          <Label htmlFor="approver-role" size="sm">Role</Label>
          <Combobox id="approver-role" testId={f('approver_role')} options={roles} value={str(cfg.approver_role)} onValueChange={(v) => patch({ approver_role: v })} placeholder="Choose a role..." searchPlaceholder="Search roles..." emptyText={roles.length ? 'No matching role.' : 'No roles are available to choose from.'} />
          <FieldHint testId="flow-hint-approver-role">Roles are managed by your administrator.</FieldHint>
          <Err field="approver_role" />
        </div>
      )}
      {approverType === 'user' && (
        <div>
          <Label htmlFor="approver-users" size="sm">People (emails, comma-separated)</Label>
          <Input
            id="approver-users"
            data-testid={f('approver_users')}
            defaultValue={users.join(', ')}
            onChange={(e) => {
              const list = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
              patch({ approver_users: list.length ? list : undefined });
            }}
            placeholder="manager@company.com"
          />
          <FieldHint testId="flow-hint-approver-users">Use the email address each person signs in with.</FieldHint>
          <Err field="approver_users" />
        </div>
      )}
      <BranchRows nodeId={nodeId} cfgType="human.approval" cfg={cfg} />
      <Err field="branch.approve" />
      <Err field="branch.reject" />
    </Section>
  );
}
