import { FieldHint } from '../FieldHint';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';

export const ENTRY_POLICIES = [
  { value: 'new_run_each_time', label: 'Start a new run' },
  { value: 'resume_if_waiting', label: "Continue the person's waiting run" },
  { value: 'once_per_member', label: 'Only once per person' },
  { value: 'one_active_per_member', label: 'Only one run at a time per person' },
] as const;

/** "Each new message": what a message does for a person who already went through the flow. Unset = start a new run. */
export function EntryPolicyField({ value, onChange, disabled }: { value: unknown; onChange: (next: string | undefined) => void; disabled?: boolean }) {
  const current = ENTRY_POLICIES.find((p) => p.value === value)?.value ?? 'new_run_each_time';
  return (
    <div data-testid="flow-entry-policy">
      <Label htmlFor="entry-policy">Each new message</Label>
      <Select value={current} disabled={disabled} onValueChange={(v) => onChange(v === 'new_run_each_time' ? undefined : v)}>
        <SelectTrigger id="entry-policy" aria-label="Each new message" data-testid="flow-entry-policy-select">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {ENTRY_POLICIES.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
        </SelectContent>
      </Select>
      {current === 'resume_if_waiting' && (
        <FieldHint testId="flow-hint-entry-policy">If this person has a run waiting at a Wait step, their message continues it instead of starting a new run.</FieldHint>
      )}
    </div>
  );
}
