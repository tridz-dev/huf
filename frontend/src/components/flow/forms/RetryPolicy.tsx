import { RefreshCcw } from 'lucide-react';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import type { TimeUnit } from '@/lib/flow-data/flowUnits';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Checkbox } from '../../ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { FieldHint } from '../FieldHint';
import { MoreOptions } from '../frame/MoreOptions';
import { DurationField } from './fields';
import type { RetryPolicy as RetryConfig } from '../../../types/flow.types';

const DEFAULT_RETRY: RetryConfig = { attempts: 3, backoff: 'fixed', delay_seconds: 60 };
const UNITS: TimeUnit[] = ['minutes', 'hours'];

/** "Try again if it fails": how many tries, and how long to wait between them. Absent policy = no retry. */
export function RetryPolicy({ f, Err, retry, onChange }: {
  f: (field: string) => string;
  Err: (p: { field: string }) => React.ReactNode;
  retry: RetryConfig | undefined;
  onChange: (next: RetryConfig | undefined) => void;
}) {
  const { canManage } = useFlowPermissions();
  const on = retry !== undefined;
  const set = (change: Partial<RetryConfig>) => {
    const next = { ...(retry ?? DEFAULT_RETRY), ...change };
    if (next.backoff === 'fixed') delete next.max_delay_seconds;
    onChange(next);
  };
  return (
    <MoreOptions label="Try again if it fails" defaultOpen={on} testId="flow-retry-section">
      <div className="space-y-3" data-testid={f('retry')}>
        <div className="flex items-center gap-2">
          <Checkbox id="retry-on" data-testid={f('retry.on')} disabled={!canManage} checked={on} onCheckedChange={(v) => onChange(v === true ? DEFAULT_RETRY : undefined)} />
          <Label htmlFor="retry-on" size="sm" className="flex items-center gap-1.5"><RefreshCcw className="h-3.5 w-3.5" aria-hidden />Try again when this step fails</Label>
        </div>
        {retry && (
          <>
            <div>
              <Label htmlFor="retry-attempts" size="sm">Tries</Label>
              <Input
                id="retry-attempts"
                data-testid={f('retry.attempts')}
                type="number"
                inputMode="numeric"
                min={2}
                max={10}
                className="w-28"
                disabled={!canManage}
                value={Number.isFinite(retry.attempts) ? String(retry.attempts) : ''}
                onChange={(e) => set({ attempts: e.target.value.trim() === '' ? NaN : Number(e.target.value) })}
              />
              <Err field="retry.attempts" />
            </div>
            <div>
              <Label htmlFor="retry-backoff" size="sm">Wait between tries</Label>
              <Select value={retry.backoff} disabled={!canManage} onValueChange={(v) => set({ backoff: v as RetryConfig['backoff'] })}>
                <SelectTrigger id="retry-backoff" data-testid={f('retry.backoff')}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="fixed">Same each time</SelectItem>
                  <SelectItem value="exponential">Longer each time</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <DurationField
              id="retry-delay"
              testId={f('retry.delay_seconds')}
              label="First wait"
              optionalWord={false}
              units={UNITS}
              value={retry.delay_seconds}
              disabled={!canManage}
              onChange={(s) => set({ delay_seconds: s ?? 0 })}
            />
            <Err field="retry.delay_seconds" />
            {retry.backoff === 'exponential' && (
              <DurationField
                id="retry-max-delay"
                testId={f('retry.max_delay_seconds')}
                label="Longest wait"
                units={UNITS}
                value={retry.max_delay_seconds}
                disabled={!canManage}
                onChange={(s) => set({ max_delay_seconds: s })}
              />
            )}
            <FieldHint testId="flow-hint-retry">Waits are at least a minute. After the last try, the step's failure path is used.</FieldHint>
          </>
        )}
      </div>
    </MoreOptions>
  );
}
