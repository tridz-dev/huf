import { useEffect, useMemo, useRef, useState } from 'react';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Button } from '../ui/button';
import { Combobox } from '../ui/combobox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import {
  DEFAULT_PICKER,
  HOUR_STEPS,
  MINUTE_STEPS,
  WEEKDAYS,
  cronProblem,
  cronToPicker,
  pickerForKind,
  pickerToCron,
  type ScheduleKind,
  type SchedulePicker,
} from '@/lib/flow-graph/flowSchedule';
import { clock, describeCron, fixedClockTime } from '@/lib/flow-trigger/scheduleText';
import { clockInOtherZone, formatWall, nextRuns } from '@/lib/flow-trigger/scheduleRuns';
import { useSiteTimezone } from '@/lib/serverTime';
import { allTimeZones, browserTimeNote, browserZone, describeZone } from '@/lib/flow-run/flowTimeZone';
import { SCHEDULE_EXAMPLES } from '@/lib/flow/flowHelp';
import { Code, Examples, FieldHint } from './FieldHint';

const KINDS: Array<{ id: ScheduleKind; label: string }> = [
  { id: 'minutes', label: 'Every few minutes' },
  { id: 'hours', label: 'Every few hours' },
  { id: 'daily', label: 'Every day' },
  { id: 'weekly', label: 'On certain days of the week' },
  { id: 'monthly', label: 'Every month' },
  { id: 'custom', label: 'Custom' },
];

// Monday first, the way a working week is read.
const WEEK_ORDER = [1, 2, 3, 4, 5, 6, 0];
const SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const PRESETS: Array<{ id: string; label: string; days: number[] }> = [
  { id: 'weekdays', label: 'Weekdays', days: [1, 2, 3, 4, 5] },
  { id: 'weekend', label: 'Weekend', days: [0, 6] },
  { id: 'everyday', label: 'Every day', days: [0, 1, 2, 3, 4, 5, 6] },
];

interface Props {
  cron: string | undefined;
  /** The zone chosen by the author; undefined means the site's time zone. */
  timeZone?: string;
  onChange: (cron: string) => void;
  onZoneChange?: (zone: string | undefined) => void;
  disabled?: boolean;
}

const every = (n: number, unit: string) => `${n} ${unit}${n === 1 ? '' : 's'}`;

/**
 * The schedule picker: friendly choices compile to the 5-part `cron` stored on the trigger. The raw cron box only exists
 * under "Custom". Everything it says (summary, next runs, problems) is computed from the value being typed, so a fixed cron
 * clears its message at once.
 */
export function ScheduleEditor({ cron, timeZone, onChange, onZoneChange, disabled }: Props) {
  const siteZone = useSiteTimezone();
  const [picker, setPicker] = useState<SchedulePicker>(() => cronToPicker(cron));
  const [raw, setRaw] = useState(cron ?? '');
  const [touched, setTouched] = useState(false);
  const emitted = useRef(cron ?? '');

  // Follow outside changes (loading a saved flow, undo) without fighting the user's own typing.
  useEffect(() => {
    if ((cron ?? '') !== emitted.current) {
      emitted.current = cron ?? '';
      setRaw(cron ?? '');
      setPicker(cronToPicker(cron));
    }
  }, [cron]);

  const emit = (next: string) => {
    emitted.current = next;
    setRaw(next);
    onChange(next);
  };

  const update = (next: SchedulePicker) => {
    setPicker(next);
    if (next.kind !== 'custom') emit(pickerToCron(next));
  };

  const chooseKind = (kind: ScheduleKind) => {
    setTouched(true);
    if (kind === 'custom') {
      setPicker({ ...picker, kind });
      return;
    }
    // Leaving Custom: start from the friendly reading of the pattern when there is one, else from the defaults.
    const friendly = picker.kind === 'custom' ? cronToPicker(raw) : picker;
    update(pickerForKind(kind, friendly.kind === 'custom' ? DEFAULT_PICKER : friendly));
  };

  const zone = timeZone || siteZone || '';
  const zoneKnown = Boolean(zone);
  const effective = zone || browserZone();
  const problem = cronProblem(raw);
  const showProblem = problem && (touched || raw.trim() !== '');
  const valid = !problem;

  const zoneOptions = useMemo(
    () => allTimeZones(siteZone, timeZone).map((z) => ({ value: z, label: describeZone(z), subtitle: z === siteZone ? "This site's time zone" : undefined })),
    [siteZone, timeZone],
  );

  const runs = useMemo(() => (valid ? nextRuns(raw, effective, 3) : []), [valid, raw, effective]);
  const fixed = fixedClockTime(raw);
  const browserNote = fixed && zoneKnown ? browserTimeNote(clockInOtherZone(fixed.hour, fixed.minute, zone, browserZone()), zone) : '';
  const summary = valid ? describeCron(raw) : 'No valid schedule yet.';

  const setTime = (value: string) => {
    const m = /^(\d{1,2}):(\d{2})/.exec(value);
    if (!m) return;
    setTouched(true);
    update({ ...picker, hour: Math.min(23, Number(m[1])), minute: Math.min(59, Number(m[2])) });
  };

  const toggleDay = (day: number) => {
    setTouched(true);
    const has = picker.weekdays.includes(day);
    if (has && picker.weekdays.length === 1) return; // a weekly schedule needs at least one day
    update({ ...picker, weekdays: has ? picker.weekdays.filter((d) => d !== day) : [...picker.weekdays, day] });
  };

  const timeInput = (
    <div>
      <Label htmlFor="schedule-time" size="sm">At what time</Label>
      <Input
        id="schedule-time"
        data-testid="flow-field-trigger.schedule-time"
        type="time"
        step={60}
        disabled={disabled}
        value={clock(picker.hour, picker.minute)}
        onChange={(e) => setTime(e.target.value)}
      />
    </div>
  );

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground" data-testid="flow-hint-schedule-intro">
        Starts the flow by itself at the times you choose. It only runs while the flow is live.
      </p>
      <div>
        <Label htmlFor="schedule-kind" size="sm">How often</Label>
        <Select value={picker.kind} disabled={disabled} onValueChange={(v) => chooseKind(v as ScheduleKind)}>
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
          <Label htmlFor="schedule-every" size="sm">Run it every</Label>
          <Select
            value={String(picker.every)}
            disabled={disabled}
            onValueChange={(v) => {
              setTouched(true);
              update({ ...picker, every: Number(v) });
            }}
          >
            <SelectTrigger id="schedule-every" data-testid="flow-field-trigger.schedule-every">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(picker.kind === 'minutes' ? MINUTE_STEPS : HOUR_STEPS).map((n) => (
                <SelectItem key={n} value={String(n)} data-testid={`flow-option-schedule-every-${n}`}>
                  {every(n, picker.kind === 'minutes' ? 'minute' : 'hour')}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {picker.kind === 'hours' && <FieldHint testId="flow-hint-schedule-every">Counted from midnight, so 3 hours means 00:00, 03:00, 06:00 and so on.</FieldHint>}
        </div>
      )}
      {picker.kind === 'hours' && (
        <div>
          <Label htmlFor="schedule-minute" size="sm">Minutes past the hour</Label>
          <Input
            id="schedule-minute"
            data-testid="flow-field-trigger.schedule-minute"
            type="number"
            min={0}
            max={59}
            disabled={disabled}
            value={picker.minute}
            onChange={(e) => {
              setTouched(true);
              update({ ...picker, minute: Number(e.target.value || 0) });
            }}
          />
        </div>
      )}
      {picker.kind === 'weekly' && (
        <div>
          <Label size="sm" id="schedule-days-label">On these days</Label>
          <div className="mt-1 flex flex-wrap gap-1.5" role="group" aria-labelledby="schedule-days-label" data-testid="flow-field-trigger.schedule-weekday">
            {WEEK_ORDER.map((d) => {
              const on = picker.weekdays.includes(d);
              return (
                <Button
                  key={d}
                  type="button"
                  size="sm"
                  variant={on ? 'default' : 'outline'}
                  aria-pressed={on}
                  aria-label={WEEKDAYS[d]}
                  disabled={disabled}
                  data-testid={`flow-field-trigger.schedule-weekday-${d}`}
                  className="min-w-11 px-2"
                  onClick={() => toggleDay(d)}
                >
                  {SHORT[d]}
                </Button>
              );
            })}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {PRESETS.map((p) => (
              <Button
                key={p.id}
                type="button"
                size="sm"
                variant="ghost"
                disabled={disabled}
                data-testid={`flow-schedule-preset-${p.id}`}
                className="px-2 text-xs"
                onClick={() => {
                  setTouched(true);
                  update({ ...picker, weekdays: p.days });
                }}
              >
                {p.label}
              </Button>
            ))}
          </div>
        </div>
      )}
      {picker.kind === 'monthly' && (
        <div>
          <Label htmlFor="schedule-monthday" size="sm">On which day of the month</Label>
          <Select
            value={String(picker.monthday)}
            disabled={disabled}
            onValueChange={(v) => {
              setTouched(true);
              update({ ...picker, monthday: v === 'last' ? 'last' : Number(v) });
            }}
          >
            <SelectTrigger id="schedule-monthday" data-testid="flow-field-trigger.schedule-monthday">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                <SelectItem key={d} value={String(d)} data-testid={`flow-option-schedule-monthday-${d}`}>{`Day ${d}`}</SelectItem>
              ))}
              <SelectItem value="last" data-testid="flow-option-schedule-monthday-last">The last day of the month</SelectItem>
            </SelectContent>
          </Select>
          {typeof picker.monthday === 'number' && picker.monthday > 28 && (
            <FieldHint testId="flow-hint-schedule-monthday">Months that have no day {picker.monthday} are skipped. Choose "The last day of the month" to run every month.</FieldHint>
          )}
        </div>
      )}
      {['daily', 'weekly', 'monthly'].includes(picker.kind) && timeInput}

      {picker.kind === 'custom' && (
        <div>
          <Label htmlFor="cron" size="sm">Schedule pattern</Label>
          <Input
            id="cron"
            data-testid="flow-field-trigger.schedule-cron"
            className="font-mono text-xs"
            disabled={disabled}
            value={raw}
            aria-invalid={Boolean(showProblem)}
            onChange={(e) => {
              setTouched(true);
              emit(e.target.value);
            }}
            placeholder="0 9 * * 1"
          />
          <FieldHint testId="flow-hint-schedule-cron">Five parts: minute, hour, day of month, month, day of week. Use * for "every".</FieldHint>
          <Examples testId="flow-schedule-examples" title="Show examples">
            {SCHEDULE_EXAMPLES.map((ex) => (
              <p key={ex.cron}><Code>{ex.cron}</Code> {ex.meaning}</p>
            ))}
          </Examples>
        </div>
      )}

      <div>
        <Label htmlFor="schedule-zone" size="sm">Time zone</Label>
        <Combobox
          id="schedule-zone"
          testId="flow-field-trigger.schedule-zone"
          options={zoneOptions}
          value={zone}
          disabled={disabled || !onZoneChange}
          placeholder="This site's time zone"
          searchPlaceholder="Search time zones..."
          emptyText="No time zone with that name."
          onValueChange={(v) => {
            setTouched(true);
            onZoneChange?.(!v || v === siteZone ? undefined : v);
          }}
        />
        <FieldHint testId="flow-hint-schedule-zone">Times above are read on this clock. It starts as this site's time zone.</FieldHint>
      </div>

      <div className="rounded-md border border-line bg-muted/30 p-2.5 space-y-1" data-testid="flow-schedule-preview">
        <p className="text-sm font-medium text-ink break-words" data-testid="flow-schedule-summary">
          {valid && zoneKnown ? `${summary} in ${zone}` : summary}
        </p>
        {browserNote && <p className="text-xs text-muted-foreground" data-testid="flow-schedule-timezone">{browserNote}</p>}
        {runs.length > 0 && (
          <div className="text-xs text-muted-foreground" data-testid="flow-schedule-next-runs">
            <p className="font-medium">Next runs{zoneKnown ? ` (${zone})` : ''}</p>
            <ul className="mt-0.5 space-y-0.5">
              {runs.map((r) => (
                <li key={r.at.toISOString()} data-testid="flow-schedule-next-run">{formatWall(r.wall)}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {showProblem ? (
        <p role="alert" className="text-meta text-destructive" data-testid="flow-error-trigger.schedule-cron">
          {problem}
        </p>
      ) : null}
    </div>
  );
}
