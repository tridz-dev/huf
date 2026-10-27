import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock } from 'lucide-react';
import { toast } from 'sonner';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Combobox } from './ui/combobox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { clearFlowTrigger, getFlowTrigger, setFlowTrigger } from '../services/flowApi';
import {
  DOC_EVENTS,
  DEFAULT_DOC_EVENT_FORM,
  DEFAULT_SCHEDULE_FORM,
  describeTriggerState,
  docEventFormToArgs,
  scheduleFormToArgs,
  summaryToDocEventForm,
  summaryToNodeConfig,
  summaryToScheduleForm,
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
  /** Canonical node config (cron / doctype+event) after a hydrate / save / clear succeeds; null when there is none. */
  onSynced?: (config: ReturnType<typeof summaryToNodeConfig>) => void;
}

/**
 * Schedule / doc-event trigger editor. State lives in the backend (an Automation bound to the
 * flow's converted Procedure), not in the node config, so it hydrates from get_flow_trigger
 * and writes through set_flow_trigger.
 */
export function FlowTriggerPanel({ kind, flowId, hasUnsavedChanges, docTypes, loadingDocTypes, onSynced }: FlowTriggerPanelProps) {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<FlowTriggerSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<TriggerErrorInfo | null>(null);
  const [scheduleForm, setScheduleForm] = useState<ScheduleForm>(DEFAULT_SCHEDULE_FORM);
  const [docForm, setDocForm] = useState<DocEventForm>(DEFAULT_DOC_EVENT_FORM);

  // Latest callback without refetching when its identity changes (it closes over the selected node).
  const syncedRef = useRef(onSynced);
  syncedRef.current = onSynced;

  const hydrate = useCallback((s: FlowTriggerSummary | null) => {
    setSummary(s);
    setScheduleForm(summaryToScheduleForm(s));
    setDocForm(summaryToDocEventForm(s));
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
        syncedRef.current?.(summaryToNodeConfig(kind, s));
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
      syncedRef.current?.(summaryToNodeConfig(kind, next));
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
      syncedRef.current?.(null);
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
      {disabledReason ? <p className="text-xs text-muted-foreground">{disabledReason}</p> : null}

      {kind === 'schedule' ? (
        <>
          <div>
            <Label htmlFor="cron">Cron expression</Label>
            <Input
              id="cron"
              disabled={formDisabled}
              value={scheduleForm.cron}
              onChange={(e) => setScheduleForm({ cron: e.target.value })}
              placeholder="0 */6 * * *"
            />
          </div>
        </>
      ) : (
        <>
          <div>
            <Label htmlFor="doctype">Document type</Label>
            <Combobox
              id="doctype"
              options={docTypes}
              value={docForm.referenceDoctype}
              onValueChange={(v) => setDocForm({ ...docForm, referenceDoctype: v })}
              placeholder={loadingDocTypes ? 'Loading...' : 'Select DocType...'}
              disabled={formDisabled || loadingDocTypes}
              searchPlaceholder="Search DocType..."
              emptyText="No DocType found."
            />
          </div>
          <div>
            <Label htmlFor="doc-event">Event</Label>
            <Select
              value={docForm.docEvent}
              disabled={formDisabled}
              onValueChange={(v) => setDocForm({ ...docForm, docEvent: v as FlowDocEvent })}
            >
              <SelectTrigger id="doc-event">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DOC_EVENTS.map((e) => (
                  <SelectItem key={e} value={e}>
                    {e}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="doc-condition">Condition (optional)</Label>
            <Input
              id="doc-condition"
              disabled={formDisabled}
              value={docForm.condition}
              onChange={(e) => setDocForm({ ...docForm, condition: e.target.value })}
              placeholder="doc.status == 'Open'"
            />
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
        <Button size="sm" disabled={formDisabled} onClick={save}>
          {summary ? 'Save trigger' : 'Set trigger'}
        </Button>
        {summary ? (
          <Button size="sm" variant="outline" disabled={formDisabled} onClick={clear}>
            Clear
          </Button>
        ) : null}
      </div>
    </div>
  );
}
