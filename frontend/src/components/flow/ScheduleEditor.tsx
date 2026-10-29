import { useEffect, useState } from 'react';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import {
  WEEKDAYS,
  cronProblem,
  cronToPicker,
  describeCron,
  pickerToCron,
  type ScheduleKind,
  type SchedulePicker,
} from '@/lib/flow-graph/flowSchedule';
import { useSiteTimezone } from '@/lib/serverTime';
import { scheduleZoneSentence } from '@/lib/flow-run/flowTimeZone';
import { SCHEDULE_EXAMPLES } from '@/lib/flow/flowHelp';
import { Code, Examples, FieldHint } from './FieldHint';

const KINDS: Array<{ id: ScheduleKind; label: string }> = [
  { id: 'minutes', label: 'Every few minutes' },
  { id: 'hours', label: 'Every few hours' },
  { id: 'daily', label: 'Every day' },
  { id: 'weekly', label: 'Every week' },
  { id: 'monthly', label: 'Every month' },
  { id: 'custom', label: 'Custom (cron)' },
];

interface Props {
  cron: string | undefined;
  onChange: (cron: string) => void;
  disabled?: boolean;
  error?: string | null;
}

const num = (v: string) => (v === '' ? 0 : Number(v));

/** Friendly interval picker that compiles to the 5-part `cron` stored on the trigger, plus a raw cron box. */
export function ScheduleEditor({ cron, onChange, disabled, error }: Props) {
  const siteZone = useSiteTimezone();
  const [picker, setPicker] = useState<SchedulePicker>(() => cronToPicker(cron));
  const [raw, setRaw] = useState(cron ?? '');

  // Follow outside changes (hydration, undo) without fighting the user's own typing.
  useEffect(() => {
    if ((cron ?? '') !== raw && picker.kind !== 'custom') {
      setRaw(cron ?? '');
      setPicker(cronToPicker(cron));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cron]);

  const update = (next: SchedulePicker) => {
    setPicker(next);
    if (next.kind === 'custom') return;
    const c = pickerToCron(next);
    setRaw(c);
    onChange(c);
  };

  const showTime = ['daily', 'weekly', 'monthly'].includes(picker.kind);
  const problem = error ?? (cron ? cronProblem(cron) : null);

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground" data-testid="flow-hint-schedule-intro">
        Starts the flow by itself at the times you choose. It only runs while the flow is published.
      </p>
      <div>
        <Label htmlFor="schedule-kind" size="sm">How often</Label>
        <Select value={picker.kind} disabled={disabled} onValueChange={(v) => update({ ...picker, kind: v as ScheduleKind })}>
          <SelectTrigger id="schedule-kind" data-testid="flow-field-trigger.schedule-frequency">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {KINDS.map((k) => (
              <SelectItem key={k.id} value={k.id} data-testid={`flow-option-schedule-frequency-${k.id}`}>
                {k.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {(picker.kind === 'minutes' || picker.kind === 'hours') && (
        <div>
          <Label htmlFor="schedule-every" size="sm">Every how many {picker.kind}</Label>
          <Input
            id="schedule-every"
            data-testid="flow-field-trigger.schedule-every"
            type="number"
            min={1}
            max={picker.kind === 'minutes' ? 59 : 23}
            disabled={disabled}
            value={picker.every}
            onChange={(e) => update({ ...picker, every: num(e.target.value) })}
          />
        </div>
      )}
      {picker.kind === 'hours' && (
        <div>
          <Label htmlFor="schedule-minute" size="sm">At minute</Label>
          <Input
            id="schedule-minute"
            data-testid="flow-field-trigger.schedule-minute"
            type="number"
            min={0}
            max={59}
            disabled={disabled}
            value={picker.minute}
            onChange={(e) => update({ ...picker, minute: num(e.target.value) })}
          />
        </div>
      )}
      {picker.kind === 'weekly' && (
        <div>
          <Label htmlFor="schedule-weekday" size="sm">On</Label>
          <Select value={String(picker.weekday)} disabled={disabled} onValueChange={(v) => update({ ...picker, weekday: Number(v) })}>
            <SelectTrigger id="schedule-weekday" data-testid="flow-field-trigger.schedule-weekday">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WEEKDAYS.map((d, i) => (
                <SelectItem key={d} value={String(i)}>{d}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      {picker.kind === 'monthly' && (
        <div>
          <Label htmlFor="schedule-monthday" size="sm">On day of the month (1-28)</Label>
          <Input
            id="schedule-monthday"
            data-testid="flow-field-trigger.schedule-monthday"
            type="number"
            min={1}
            max={28}
            disabled={disabled}
            value={picker.monthday}
            onChange={(e) => update({ ...picker, monthday: num(e.target.value) })}
          />
        </div>
      )}
      {showTime && (
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label htmlFor="schedule-hour" size="sm">Hour (0-23)</Label>
            <Input
              id="schedule-hour"
              data-testid="flow-field-trigger.schedule-hour"
              type="number"
              min={0}
              max={23}
              disabled={disabled}
              value={picker.hour}
              onChange={(e) => update({ ...picker, hour: num(e.target.value) })}
            />
          </div>
          <div>
            <Label htmlFor="schedule-minute" size="sm">Minute (0-59)</Label>
            <Input
              id="schedule-minute"
              data-testid="flow-field-trigger.schedule-minute"
              type="number"
              min={0}
              max={59}
              disabled={disabled}
              value={picker.minute}
              onChange={(e) => update({ ...picker, minute: num(e.target.value) })}
            />
          </div>
        </div>
      )}

      <div>
        <Label htmlFor="cron" size="sm">Schedule expression (cron)</Label>
        <Input
          id="cron"
          data-testid="flow-field-trigger.schedule-cron"
          className="font-mono text-xs"
          disabled={disabled}
          value={raw}
          onChange={(e) => {
            setRaw(e.target.value);
            setPicker((p) => (cronToPicker(e.target.value).kind === 'custom' ? { ...p, kind: 'custom' } : cronToPicker(e.target.value)));
            onChange(e.target.value);
          }}
          placeholder="0 9 * * 1"
        />
        <FieldHint testId="flow-hint-schedule-cron">Five parts: minute, hour, day of month, month, day of week. The boxes above fill this in for you.</FieldHint>
        <Examples testId="flow-schedule-examples" title="Show examples">
          {SCHEDULE_EXAMPLES.map((ex) => (
            <p key={ex.cron}><Code>{ex.cron}</Code> {ex.meaning}</p>
          ))}
        </Examples>
      </div>

      <p className="text-xs text-muted-foreground" data-testid="flow-schedule-preview">
        {describeCron(cron)}
      </p>
      <p className="text-xs text-muted-foreground" data-testid="flow-schedule-timezone">
        {scheduleZoneSentence(siteZone)}
      </p>
      {problem ? (
        <p role="alert" className="text-meta text-destructive" data-testid="flow-error-trigger.schedule-cron">
          {problem}
        </p>
      ) : null}
    </div>
  );
}
