import { useEffect, useMemo, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { APPROVER_TYPE_HELP } from '@/lib/flow/flowHelp';
import { ApprovalCardPreview, type PreviewFact } from './ApprovalCardPreview';
import { ApproverUsersField } from './ApproverUsersField';
import { Button } from '../../../ui/button';
import { Combobox } from '../../../ui/combobox';
import { DataInput } from '../../data/DataInput';
import { ValueField } from '../fields';
import { FieldHint } from '../../FieldHint';
import { Input } from '../../../ui/input';
import { Label } from '../../../ui/label';
import { requestFocus } from '../../frame/frameStore';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../ui/select';
import { fromTextRefs, toTextRefs } from '@/lib/flow-data/textRefs';
import { getApproverRoles } from '../../../../services/flowApi';
import { describeChip, previewOf, type PickerModel } from '@/lib/flow-data/model';
import { parseValue } from '@/lib/flow-data/chips';
import { durationWords } from '@/lib/flow-data/flowUnits';
import { type ActionFormProps, BranchRows, type Opt, Section, str } from '../formKit';
import { useAsValue } from '../useAsValue';
import { useDataCatalog } from '../../data/useDataCatalog';
import { useFlowContext } from '../../../../contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';

const MAX_DETAILS = 6;
const TIMEOUT_UNITS = ['minutes', 'hours', 'days'] as const;

/** What each role means, in the words of someone who does not manage the system. */
const ROLE_WORDS: Record<string, string> = {
  'System Manager': 'Can manage everything',
  'Huf Manager': 'Manages flows and agents',
  'Huf User': 'Uses flows and agents',
  'Huf Viewer': 'Can look but not change',
};

interface Detail { label?: string; value?: unknown }

/** The words a value will read as, with the examples the step has ("Ada Lovelace"); unknown parts read `[Name: no sample yet]`. */
function sampleText(value: unknown, model: PickerModel): string {
  const parsed = parseValue(value);
  return previewOf(parsed.segments, model).text;
}

export function ApprovalForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const [roles, setRoles] = useState<Array<Opt & { subtitle?: string }>>([]);
  const { activeFlow } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const { model } = useDataCatalog(nodeId);

  useEffect(() => {
    getApproverRoles()
      .then((l) => setRoles((l || []).filter((r) => !r.name.startsWith('_Test')).map((r) => ({ value: r.name, label: r.name, subtitle: ROLE_WORDS[r.name] ?? (r.group === 'Huf' ? 'Huf role' : undefined) }))))
      .catch(() => setRoles([]));
  }, []);

  const approverType = str(cfg.approver_type);
  const users = Array.isArray(cfg.approver_users) ? (cfg.approver_users as string[]) : [];
  const details: Detail[] = Array.isArray(cfg.details) ? (cfg.details as Detail[]) : [];
  const [message, toMessage] = useAsValue(str(cfg.message), toTextRefs, (v) => fromTextRefs(v) ?? '');
  const [cardTitle, toTitle] = useAsValue(str(cfg.title), toTextRefs, (v) => fromTextRefs(v));
  const setDetails = (next: Detail[]) => patch({ details: next.length ? next : undefined });

  const timeoutMs = typeof cfg.timeout_ms === 'number' ? cfg.timeout_ms : undefined;

  // ---- the live card ----
  const flowName = activeFlow?.name || 'this flow';
  const preview = useMemo(() => {
    const t = sampleText(toTextRefs(str(cfg.title)), model).trim();
    const note = sampleText(toTextRefs(str(cfg.message)), model).trim();
    const facts: PreviewFact[] = details
      .map((d, i): PreviewFact | null => {
        const text = sampleText(d.value, model).trim();
        if (!text) return null;
        const segs = parseValue(d.value).segments;
        const only = segs.length === 1 && segs[0].kind === 'chip' ? describeChip(segs[0].chip, model).label : '';
        return { label: (d.label ?? '').trim() || only.split(' > ')[0] || `Detail ${i + 1}`, value: text };
      })
      .filter((x): x is PreviewFact => x !== null);
    return { title: t || `Approval needed: ${flowName}`, note: note || `${flowName} is waiting for your decision.`, facts };
  }, [cfg.title, cfg.message, details, model, flowName]);

  return (
    <Section title={title} hint="Pauses the flow until someone approves or rejects. Approved and Rejected are separate paths. Approvers see the request in the bell menu at the top, in their email, and on the run's page.">
      <ValueField
        field="message"
        f={f}
        Err={Err}
        nodeId={nodeId}
        label="What should the approver decide?"
        hintTestId="flow-hint-approval-message"
        kind="longtext"
        placeholder="Approve a refund of $450 for Ada Lovelace?"
        hint="Say what is being approved, with the key facts first. Add details with + Use data."
        value={message}
        onChange={(v) => patch({ message: toMessage(v) })}
      />
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
            <SelectItem value="role" description="Everyone who has the role can answer." data-testid="flow-option-approver-role">People with a role</SelectItem>
            <SelectItem value="user" description="Only the people you pick." data-testid="flow-option-approver-user">Specific people</SelectItem>
          </SelectContent>
        </Select>
        <FieldHint testId="flow-hint-approver-type">{APPROVER_TYPE_HELP[approverType] ?? 'Pick a role (everyone who has it can answer) or choose specific people.'}</FieldHint>
        <Err field="approver_type" />
      </div>
      {approverType === 'role' && (
        <div>
          <Label htmlFor="approver-role" size="sm">Which role</Label>
          <Combobox id="approver-role" testId={f('approver_role')} options={roles} value={str(cfg.approver_role)} onValueChange={(v) => patch({ approver_role: v })} placeholder="Choose a role..." searchPlaceholder="Search roles..." emptyText={roles.length ? 'No role with that name.' : 'No roles are available to choose from.'} />
          <FieldHint testId="flow-hint-approver-role">Everyone who has this role can answer. Your administrator decides who has which role.</FieldHint>
          <Err field="approver_role" />
        </div>
      )}
      {approverType === 'user' && (
        <ApproverUsersField value={users} onChange={(next) => patch({ approver_users: next })} testId={f('approver_users')} Err={<Err field="approver_users" />} disabled={!canManage} />
      )}

      <div className="space-y-3 rounded-lg border border-border p-3" data-testid="flow-approval-card-section">
        <div>
          <p className="text-sm font-semibold">What the approver sees</p>
          <FieldHint>The request appears as a card in the bell, in the email and on the run page.</FieldHint>
        </div>
        <ValueField
          field="title"
          f={f}
          Err={Err}
          nodeId={nodeId}
          label="Title"
          optional
          placeholder={`Approval needed: ${flowName}`}
          hint="The headline of the card. Leave empty to use the flow's name."
          value={cardTitle}
          onChange={(v) => patch({ title: toTitle(v) })}
        />
        <div className="space-y-2" data-testid={f('details')}>
          <Label size="sm">Show these details to the approver (optional)</Label>
          <FieldHint testId="flow-hint-approval-details">Pick up to {MAX_DETAILS} facts, like the amount or the customer. Leave this empty and Huf shows the few most telling facts for you.</FieldHint>
          {details.map((d, i) => (
            <div key={i} className="space-y-1.5 rounded-md border border-border p-2" data-testid={`flow-approval-detail-${i}`}>
              <div className="flex items-end gap-2">
                <div className="min-w-0 flex-1">
                  <Label htmlFor={`approval-detail-label-${i}`} size="sm">Label</Label>
                  <Input id={`approval-detail-label-${i}`} data-testid={f(`details.${i}.label`)} value={d.label ?? ''} maxLength={60} placeholder="Amount" disabled={!canManage} onChange={(e) => setDetails(details.map((x, j) => (j === i ? { ...x, label: e.target.value || undefined } : x)))} />
                </div>
                {canManage && (
                  <Button type="button" variant="ghost" size="sm" aria-label={`Remove detail ${i + 1}`} data-testid={f(`details.${i}.remove`)} onClick={() => setDetails(details.filter((_, j) => j !== i))}>
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>
              <DataInput id={`approval-detail-value-${i}`} nodeId={nodeId} testId={f(`details.${i}.value`)} label="Value" placeholder="Choose with + Use data" value={d.value} onChange={(v) => setDetails(details.map((x, j) => (j === i ? { ...x, value: v === '' ? undefined : v } : x)))} />
            </div>
          ))}
          {canManage && details.length < MAX_DETAILS && (
            <Button type="button" variant="outline" size="sm" className="w-full" data-testid={f('details.add')} onClick={() => setDetails([...details, { value: '' }])}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Add a detail
            </Button>
          )}
          {details.length >= MAX_DETAILS && <FieldHint>That is the most the card can show.</FieldHint>}
        </div>
        <ApprovalCardPreview title={preview.title} note={preview.note} facts={preview.facts} />
      </div>

      <BranchRows nodeId={nodeId} cfgType="human.approval" cfg={cfg} />
      <Err field="branch.approve" />
      <Err field="branch.reject" />

      <div className="flex items-start justify-between gap-3 rounded-md border border-border p-2.5" data-testid="flow-approval-timeout-summary">
        <div className="min-w-0 text-xs">
          <p className="font-medium text-foreground">If nobody answers</p>
          <p className="mt-0.5 text-muted-foreground break-words" data-testid="flow-approval-timeout-summary-text">
            {timeoutMs !== undefined
              ? `After ${durationWords(timeoutMs / 1000, [...TIMEOUT_UNITS])} the flow follows the "Timed out" path.`
              : 'The flow waits as long as it takes.'}
          </p>
        </div>
        {canManage && (
          <Button type="button" variant="outline" size="sm" className="shrink-0" data-testid="flow-approval-timeout-edit" onClick={() => requestFocus(nodeId, 'timeout_ms')}>
            {timeoutMs !== undefined ? 'Change' : 'Set a time limit'}
          </Button>
        )}
      </div>
    </Section>
  );
}
