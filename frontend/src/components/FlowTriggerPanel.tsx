import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock } from 'lucide-react';
import { toast } from 'sonner';
import { ScheduleEditor } from './flow/ScheduleEditor';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Combobox } from './ui/combobox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { clearFlowTrigger, getFlowTrigger, setFlowTrigger } from '../services/flowApi';
import {
  DOC_EVENTS,
  DEFAULT_DOC_EVENT_FORM,
  describeTriggerState,
  docEventFormToArgs,
  scheduleFormToArgs,
  summaryToNodeConfig,
  triggerDisabledReason,
  triggerErrorInfo,
  type DocEventForm,
  type FlowDocEvent,
  type FlowTriggerSummary,
  type ScheduleForm,
  type TriggerErrorInfo,
} from '../lib/flowTrigger';

interface FlowTriggerPanelProps {
  kind: 'schedule' | 'doc-event';
  flowId: string | null | undefined;
  hasUnsavedChanges: boolean;
  docTypes: Array<{ value: string; label: string }>;
  loadingDocTypes: boolean;
  /** The node's own config (the contract fields: cron, or doctype + event). The form edits it directly. */
  value: { cron?: string; doctype?: string; event?: string };
  onChange: (patch: Record<string, unknown>) => void;
  /** Inline validation messages by contract field. */
  errors?: Record<string, string | undefined>;
}

const EVENT_LABELS: Record<FlowDocEvent, string> = {
  after_insert: 'When a record is created',
  on_update: 'When a record is updated',
  on_submit: 'When a record is submitted',
  on_cancel: 'When a record is cancelled',
  on_trash: 'When a record is deleted',
};

/**
 * Schedule / doc-event trigger editor. State lives in the backend (an Automation bound to the
 * flow's converted Procedure), not in the node config, so it hydrates from get_flow_trigger
 * and writes through set_flow_trigger.
 */
export function FlowTriggerPanel({ kind, flowId, hasUnsavedChanges, docTypes, loadingDocTypes, value, onChange, errors = {} }: FlowTriggerPanelProps) {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<FlowTriggerSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<TriggerErrorInfo | null>(null);
  // The node config is the single source of truth for the form; the saved trigger only seeds an empty node.
  const scheduleForm: ScheduleForm = { cron: value.cron ?? '' };
  const docForm: DocEventForm = {
    ...DEFAULT_DOC_EVENT_FORM,
    referenceDoctype: value.doctype ?? '',
    docEvent: (DOC_EVENTS.find((e) => e === value.event) ?? DEFAULT_DOC_EVENT_FORM.docEvent) as FlowDocEvent,
  };

  const changeRef = useRef(onChange);
  changeRef.current = onChange;
  const valueRef = useRef(value);
  valueRef.current = value;

  const hydrate = useCallback((s: FlowTriggerSummary | null) => {
    setSummary(s);
  }, []);

  useEffect(() => {
    setError(null);
    if (!flowId) {
      hydrate(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getFlowTrigger(flowId)
      .then((s) => {
        if (cancelled) return;
        hydrate(s);
        const mirror = summaryToNodeConfig(kind, s);
        const v = valueRef.current;
        if (mirror && !(v.cron || v.doctype)) changeRef.current(mirror);
      })
      .catch((e) => !cancelled && setError(triggerErrorInfo(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [flowId, kind, hydrate]);

  const disabledReason = triggerDisabledReason(flowId, hasUnsavedChanges);
  const state = describeTriggerState(summary);
  // A saved trigger of the other kind is replaced on save; say so rather than silently overwrite.
  const otherKind =
    summary && (kind === 'schedule' ? summary.trigger_type === 'Doc Event' : summary.trigger_type === 'Schedule');

  const save = async () => {
    if (!flowId) return;
    const built = kind === 'schedule' ? scheduleFormToArgs(flowId, scheduleForm) : docEventFormToArgs(flowId, docForm);
    if (!built.ok) {
      setError({ kind: 'other', message: built.error });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await setFlowTrigger(built.args);
      hydrate(next);
      toast.success(next.enabled && next.automation_status === 'Active' ? 'Trigger saved' : 'Trigger saved, activation pending');
    } catch (e) {
      setError(triggerErrorInfo(e));
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    if (!flowId) return;
    setBusy(true);
    setError(null);
    try {
      await clearFlowTrigger(flowId);
      hydrate(null);
      toast.success('Trigger removed');
    } catch (e) {
      setError(triggerErrorInfo(e));
    } finally {
      setBusy(false);
    }
  };

  const openProcedure = (name: string) => navigate(`/procedures/${encodeURIComponent(name)}`);
  const formDisabled = Boolean(disabledReason) || busy || loading;

  return (
    <div className="space-y-3">
      {disabledReason ? <p className="text-xs text-muted-foreground" data-testid="flow-trigger-disabled-reason">{disabledReason}</p> : null}

      {kind === 'schedule' ? (
        <ScheduleEditor
          cron={value.cron}
          error={errors.cron}
          onChange={(cron) => onChange({ cron })}
        />
      ) : (
        <>
          <div>
            <Label htmlFor="doctype">Document type</Label>
            <Combobox
              id="doctype"
              testId="flow-field-trigger.doc-event-doctype"
              options={docTypes}
              value={docForm.referenceDoctype}
              onValueChange={(v) => onChange({ doctype: v })}
              placeholder={loadingDocTypes ? 'Loading...' : 'Select a document type...'}
              disabled={loadingDocTypes}
              searchPlaceholder="Search document types..."
              emptyText="No document type found."
            />
            {errors.doctype ? (
              <p role="alert" className="mt-1 text-[11px] text-destructive" data-testid="flow-error-trigger.doc-event-doctype">{errors.doctype}</p>
            ) : null}
          </div>
          <div>
            <Label htmlFor="doc-event">When it fires</Label>
            <Select value={value.event ?? ''} onValueChange={(v) => onChange({ event: v })}>
              <SelectTrigger id="doc-event" data-testid="flow-field-trigger.doc-event-event">
                <SelectValue placeholder="Choose an event..." />
              </SelectTrigger>
              <SelectContent>
                {DOC_EVENTS.map((e) => (
                  <SelectItem key={e} value={e} data-testid={`flow-option-doc-event-${e}`}>
                    {EVENT_LABELS[e]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.event ? (
              <p role="alert" className="mt-1 text-[11px] text-destructive" data-testid="flow-error-trigger.doc-event-event">{errors.event}</p>
            ) : null}
          </div>
        </>
      )}

      {otherKind ? (
        <p className="text-xs text-muted-foreground">
          This flow already has a {summary?.trigger_type} trigger. Saving replaces it.
        </p>
      ) : null}

      {error ? (
        <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
          {error.message}
        </div>
      ) : null}

      {!otherKind && summary ? (
        <div
          role="status"
          className="rounded-md border border-border bg-paper p-2 text-xs space-y-1.5"
        >
          <p className={state.kind === 'live' ? 'font-medium' : 'text-muted-foreground'}>{state.message}</p>
          {state.kind === 'activation_required' ? (
            <div className="flex flex-wrap items-center gap-2">
              {state.procedure ? (
                <Button size="sm" variant="outline" onClick={() => openProcedure(state.procedure!)}>
                  Open Procedure
                </Button>
              ) : null}
              <Button size="sm" variant="outline" disabled={formDisabled} onClick={save}>
                Retry activation
              </Button>
            </div>
          ) : null}
          {summary.stale ? (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-muted-foreground">The flow changed since this trigger was applied; it still runs the old version.</p>
              <Button size="sm" variant="outline" disabled={formDisabled} onClick={save}>
                Re-apply
              </Button>
            </div>
          ) : null}
          {kind === 'schedule' && summary.next_run && state.kind === 'live' ? (
            <p className="flex items-center gap-1.5 text-muted-foreground">
              <Clock className="w-3 h-3 shrink-0" />
              Next run: {summary.next_run} (server time)
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="flex gap-2">
        <Button size="sm" data-testid="flow-trigger-apply" disabled={formDisabled} onClick={save}>
          {summary ? 'Update trigger' : 'Activate trigger'}
        </Button>
        {summary ? (
          <Button size="sm" variant="outline" data-testid="flow-trigger-clear" disabled={formDisabled} onClick={clear}>
            Clear
          </Button>
        ) : null}
      </div>
    </div>
  );
}
