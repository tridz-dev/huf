import { AlertTriangle, ArrowRight, Pin, PinOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { HumanValue } from '@/components/common/HumanValue';
import { StatusPill } from '@/components/common/StatusPill';
import { GATEWAY_LABELS, isGatewayOutput, splitGatewayOutput } from '@/lib/flow-test/gatewayResult';
import { ageText, durationText } from '@/lib/flow-test/testModel';
import { describeCron } from '@/lib/flow-trigger/scheduleText';
import { formatAbsoluteTime } from '@/lib/serverTime';
import type { StepTestResult } from '@/services/flow/stepTestApi';

/** A skipped step's output without the "Would ..." wording (that sentence is shown above it). */
/** A simulated schedule tick in plain words: when it fired and the schedule as a sentence, not the step id or the cron text. */
export function scheduleTickRows(out: Record<string, unknown>): Record<string, string> | null {
  if (!('scheduled_for' in out && 'trigger_node' in out && 'cron' in out)) return null;
  const when = typeof out.scheduled_for === 'string' ? formatAbsoluteTime(out.scheduled_for) : '';
  const rows: Record<string, string> = {};
  if (when) rows['When it fires'] = when;
  const cron = typeof out.cron === 'string' ? out.cron : '';
  const text = cron ? describeCron(cron) : '';
  if (text && !text.startsWith('No valid')) rows.Schedule = `Runs ${text.charAt(0).toLowerCase()}${text.slice(1)}`;
  return rows;
}

function shownOutput(result: StepTestResult): unknown {
  const out = result.output;
  if (result.mode !== 'simulated' || !out || typeof out !== 'object' || Array.isArray(out)) return out;
  const tick = scheduleTickRows(out as Record<string, unknown>);
  if (tick) return tick;
  return Object.fromEntries(Object.entries(out as Record<string, unknown>).filter(([key]) => !['simulated', 'summary', 'note'].includes(key)));
}

export interface PinState {
  /** The step already has a pinned sample (and when it was pinned). */
  pinned: boolean;
  pinnedAt?: string;
  onPin: () => void;
  onUnpin: () => void;
}

/**
 * What one test did: succeeded or failed, how long it took, a plain sentence for a skipped step, the output as
 * labelled rows (the exact data one click away behind Raw) and the pin controls. A failed test says what went wrong
 * in plain words and what to do about it.
 */
export function TestResultView({ result, pin, onOpenSetup, isTrigger }: { result: StepTestResult; pin: PinState; onOpenSetup: () => void; isTrigger: boolean }) {
  const failed = result.status === 'failed';
  const preview = result.preview;
  const chat = isTrigger && isGatewayOutput(result.output) ? splitGatewayOutput(result.output) : null;
  const canPin = !failed && result.mode !== 'preview' && result.pin_value !== null && result.pin_value !== undefined;
  return (
    <div className="space-y-3" data-testid="flow-step-test-result" data-status={result.status} data-mode={result.mode}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1" role="status" aria-live="polite">
        {failed ? (
          <StatusPill kind="failed" label="Failed" data-testid="flow-step-test-status" />
        ) : (
          <StatusPill kind="finished" label={result.mode === 'simulated' ? 'Succeeded (simulated)' : 'Succeeded'} data-testid="flow-step-test-status" />
        )}
        {result.mode === 'simulated' && !failed && <Badge variant="pill-neutral" data-testid="flow-step-test-simulated">Nothing was sent</Badge>}
        <span className="text-meta text-muted-foreground" data-testid="flow-step-test-duration">
          {[result.duration_ms > 0 ? `Took ${durationText(result.duration_ms)}` : '', `Tested ${ageText(result.tested_at)}`].filter(Boolean).join(' · ')}
        </span>
      </div>

      {result.warnings?.length > 0 && (
        <ul className="space-y-1 rounded-md border border-warning/30 bg-warning-tint p-2.5 text-xs text-warning" data-testid="flow-step-test-warnings">
          {result.warnings.map((w) => (
            <li key={w} className="flex items-start gap-2"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden /><span>{w}</span></li>
          ))}
        </ul>
      )}

      {failed && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm" data-testid="flow-step-test-error">
          <p className="flex items-start gap-2 break-words text-foreground">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
            <span>{result.error}</span>
          </p>
          {result.fix_hint && (
            <p className="mt-2 text-xs text-muted-foreground" data-testid="flow-step-test-fix">
              <span className="font-medium text-foreground">How to fix it: </span>
              {result.fix_hint}
            </p>
          )}
          {!isTrigger && (
            <Button type="button" variant="outline" size="sm" className="mt-2" onClick={onOpenSetup} data-testid="flow-step-test-open-setup">
              Open Setup
            </Button>
          )}
        </div>
      )}

      {!failed && result.summary && (
        <p className="text-sm font-medium break-words" data-testid="flow-step-test-summary">{result.summary}</p>
      )}

      {!failed && result.branch && (
        <p className="text-sm" data-testid="flow-step-test-branch">
          The answer is <span className="font-semibold">{result.branch}</span>.
        </p>
      )}
      {!failed && result.goes_to && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground" data-testid="flow-step-test-goes-to">
          <ArrowRight className="h-3.5 w-3.5" aria-hidden /> Next step: {result.goes_to}
        </p>
      )}

      {preview && (
        <div className="rounded-md border border-border bg-muted/30 p-3 text-sm" data-testid="flow-step-test-approval">
          <p className="mb-1.5 text-meta text-muted-foreground">What the approver would see</p>
          <p className="font-medium break-words" data-testid="flow-step-test-approval-title">{preview.title}</p>
          {preview.note && <p className="mt-1 text-xs text-muted-foreground break-words">{preview.note}</p>}
          {preview.facts.length > 0 && (
            <dl className="mt-2 grid grid-cols-[minmax(0,max-content)_minmax(0,1fr)] gap-x-4 gap-y-1 text-xs" data-testid="flow-step-test-approval-facts">
              {preview.facts.map((f) => (
                <div key={f.label} className="contents">
                  <dt className="text-muted-foreground">{f.label}</dt>
                  <dd className="break-words">{f.value}</dd>
                </div>
              ))}
            </dl>
          )}
          <p className="mt-2 text-xs text-muted-foreground" data-testid="flow-step-test-approval-who">Who can decide: {preview.who_can_decide}</p>
        </div>
      )}

      {!failed && !preview && (
        <div>
          <h4 className="mb-1.5 text-xs font-medium text-muted-foreground">{isTrigger ? 'What the flow starts with' : 'Output'}</h4>
          <HumanValue
            value={chat ? chat.main : shownOutput(result)}
            rawValue={result.output}
            raw
            rawTitle="Raw output"
            testId="flow-step-test-output"
            emptyText="This step did not hand any data to the next step."
            labels={chat ? GATEWAY_LABELS : undefined}
          />
          {chat && Object.keys(chat.details).length > 0 && (
            <details className="mt-2 text-xs" data-testid="flow-step-test-details">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Details</summary>
              <HumanValue value={chat.details} labels={GATEWAY_LABELS} testId="flow-step-test-details-rows" className="mt-2" />
            </details>
          )}
          {result.output_shortened && <p className="mt-1 text-meta text-muted-foreground" data-testid="flow-step-test-shortened">Long values were shortened here.</p>}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2" data-testid="flow-step-pin-area">
        {canPin && (
          <Button type="button" variant="outline" size="sm" onClick={pin.onPin} data-testid="flow-step-pin">
            <Pin className="mr-1.5 h-3.5 w-3.5" aria-hidden />
            {pin.pinned ? 'Replace pinned output' : 'Pin this output'}
          </Button>
        )}
        {pin.pinned && (
          <>
            <span className="text-xs text-muted-foreground" data-testid="flow-step-pinned">
              Pinned {pin.pinnedAt ? ageText(pin.pinnedAt) : ''}
            </span>
            <Button type="button" variant="ghost" size="sm" onClick={pin.onUnpin} data-testid="flow-step-unpin">
              <PinOff className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              Unpin
            </Button>
          </>
        )}
      </div>
      {canPin && !pin.pinned && (
        <p className="text-meta text-muted-foreground">
          Pinning keeps this output as the example for the steps after it, so "Use data" shows real values.
        </p>
      )}
    </div>
  );
}
