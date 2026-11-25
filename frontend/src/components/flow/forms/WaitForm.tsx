import { useMemo } from 'react';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { allTimeZones, describeZone } from '@/lib/flow-run/flowTimeZone';
import { useSiteTimezone } from '@/lib/serverTime';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { Combobox } from '../../ui/combobox';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { FieldHint } from '../FieldHint';
import { ApprovalTimeoutField } from './approval/ApprovalTimeoutField';
import { ValueField } from './fields';
import { type ActionFormProps, asObj, Section } from './formKit';
import { useFlowContext } from '../../../contexts/FlowContext';
import { isGatewayKindId } from '@/lib/flow-gateway/gatewayWords';
import type { WaitMode } from '../../../types/flow.types';

const MODES: Array<{ mode: WaitMode; label: string }> = [
  { mode: 'duration', label: 'For a while' },
  { mode: 'until', label: 'Until a date and time' },
  { mode: 'resume', label: 'Until someone continues it' },
];
const UNITS = [
  { value: 'minutes', label: 'Minutes' },
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
];

/** The Wait step: pause for a while, until a moment, or until a person (or a request to its resume link) continues it. */
export function WaitForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const { canManage } = useFlowPermissions();
  const siteZone = useSiteTimezone();
  const { activeFlow } = useFlowContext();
  const triggerType = activeFlow?.nodes.find((n) => n.data.nodeType === 'trigger')?.data.triggerConfig?.type;
  const hasMember = isGatewayKindId(triggerType);
  const mode: WaitMode = cfg.mode === 'until' || cfg.mode === 'resume' ? cfg.mode : 'duration';
  const duration = asObj(cfg.duration);
  const resume = asObj(cfg.resume);
  const zone = typeof cfg.time_zone === 'string' ? cfg.time_zone : '';
  const zoneOptions = useMemo(
    () => allTimeZones(siteZone, zone).map((z) => ({ value: z, label: describeZone(z), subtitle: z === siteZone ? "This site's time zone" : undefined })),
    [siteZone, zone],
  );

  // Switching mode drops the other modes' settings, so nothing stale is saved.
  const setMode = (next: WaitMode) => {
    if (next === mode) return;
    patch({
      mode: next,
      duration: next === 'duration' ? { unit: 'hours' } : undefined,
      until: undefined,
      time_zone: undefined,
      resume: undefined,
    });
  };
  const setResume = (change: Record<string, unknown>) => {
    const next = { ...resume, ...change };
    for (const k of Object.keys(change)) if (change[k] === undefined) delete next[k];
    patch({ resume: Object.keys(next).length ? next : undefined });
  };

  return (
    <Section title={title} hint="Pauses the flow. It continues after a set time, at a date and time, or when someone continues it from the run page.">
      <div>
        <Label size="sm" id="wait-mode-label">Wait</Label>
        <div role="radiogroup" aria-labelledby="wait-mode-label" className="mt-1 flex flex-wrap gap-2" data-testid={f('mode')}>
          {MODES.map((m) => {
            const on = m.mode === mode;
            return (
              <button
                key={m.mode}
                type="button"
                role="radio"
                aria-checked={on}
                disabled={!canManage}
                data-testid={`${f('mode')}-${m.mode}`}
                onClick={() => setMode(m.mode)}
                className={cn(
                  'flex min-h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  on ? 'border-signal bg-signal/10 text-foreground' : 'border-border text-muted-foreground hover:text-foreground',
                )}
              >
                {m.label}
                {on && <Check className="h-3 w-3" aria-hidden />}
              </button>
            );
          })}
        </div>
      </div>

      {mode === 'duration' && (
        <div>
          <Label htmlFor="wait-duration" size="sm">How long</Label>
          <div className="flex items-center gap-2">
            <Input
              id="wait-duration"
              data-testid={f('duration.value')}
              type="number"
              inputMode="numeric"
              min={1}
              className="w-28 shrink-0"
              disabled={!canManage}
              value={typeof duration.value === 'number' ? String(duration.value) : ''}
              onChange={(e) => {
                const n = Number(e.target.value);
                patch({ duration: { ...duration, unit: duration.unit ?? 'hours', value: e.target.value.trim() === '' || !Number.isFinite(n) ? undefined : n } });
              }}
            />
            <Select value={typeof duration.unit === 'string' ? duration.unit : 'hours'} disabled={!canManage} onValueChange={(unit) => patch({ duration: { ...duration, unit } })}>
              <SelectTrigger className="min-w-0 flex-1" aria-label="Unit" data-testid={f('duration.unit')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {UNITS.map((u) => <SelectItem key={u.value} value={u.value}>{u.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <Err field="duration.value" />
          <FieldHint testId="flow-hint-wait-duration">The flow continues about a minute after this time is up.</FieldHint>
        </div>
      )}

      {mode === 'until' && (
        <>
          <ValueField
            field="until"
            f={f}
            Err={Err}
            nodeId={nodeId}
            label="Date and time"
            placeholder="2030-01-31 09:00"
            hint="If this time has already passed, the flow continues at once."
            hintTestId="flow-hint-wait-until"
            disabled={!canManage}
            value={cfg.until}
            onChange={(until) => patch({ until })}
          />
          <div>
            <Label htmlFor="wait-zone" size="sm">Time zone</Label>
            <Combobox
              id="wait-zone"
              testId={f('time_zone')}
              options={zoneOptions}
              value={zone || siteZone || ''}
              disabled={!canManage}
              placeholder="This site's time zone"
              searchPlaceholder="Search time zones..."
              emptyText="No time zone with that name."
              onValueChange={(v) => patch({ time_zone: !v || v === siteZone ? undefined : v })}
            />
          </div>
        </>
      )}

      {mode === 'resume' && (
        <>
          {resume.wait_for !== 'member_reply' && (
            <p className="rounded-md bg-muted/30 p-2 text-xs text-muted-foreground" data-testid="flow-wait-resume-info">
              Continue it from the run page, or send a request to its resume link (shown on the run once it is waiting).
            </p>
          )}
          {(hasMember || resume.wait_for === 'member_reply') && (
            <label className="flex items-center gap-2 text-xs" data-testid={f('resume.wait_for')}>
              <input
                type="checkbox"
                className="h-3.5 w-3.5"
                disabled={!canManage}
                checked={resume.wait_for === 'member_reply'}
                onChange={(e) => setResume({ wait_for: e.target.checked ? 'member_reply' : undefined })}
              />
              Or when the person replies
            </label>
          )}
          <ApprovalTimeoutField
            nodeId={nodeId}
            kind="wait"
            label="Give up after"
            timeoutMs={typeof resume.timeout_ms === 'number' ? resume.timeout_ms : undefined}
            onChange={(ms) => setResume({ timeout_ms: ms })}
            disabled={!canManage}
          />
          <Err field="resume.timeout_ms" />
        </>
      )}
    </Section>
  );
}
