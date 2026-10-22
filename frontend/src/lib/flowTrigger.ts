/**
 * Pure helpers mapping the Flow builder's trigger forms onto huf.ai.flow_api
 * set_flow_trigger / get_flow_trigger, and API state onto user-facing messages.
 *
 * Flow triggers are an Automation bound to the Flow's converted Agent Procedure, so
 * the form speaks the backend's vocabulary (5-part cron, or Hourly..Yearly + count;
 * Frappe doc-event method names) rather than the old node-config intervalType/cron fields.
 */

/**
 * Doc events a Flow trigger can use: the intersection of the backend's
 * huf.ai.automation_hooks.SUPPORTED_DOC_EVENTS and the Flow graph IR enum
 * (graph_ir.schema.json TriggerDocEventNode.config.event). The backend also accepts
 * before_insert, validate, before_save, after_save, before_submit, before_rename,
 * after_rename and after_delete, but the node config cannot hold them, so the panel does not offer them.
 */
export const DOC_EVENTS = ['after_insert', 'on_update', 'on_submit', 'on_cancel', 'on_trash'] as const;
export type FlowDocEvent = (typeof DOC_EVENTS)[number];

/** Shape returned by get_flow_trigger / set_flow_trigger (null when the flow has no trigger). */
export interface FlowTriggerSummary {
  flow_id: string;
  trigger_type: 'Schedule' | 'Doc Event';
  automation: string;
  automation_trigger: string;
  automation_status: string;
  procedure: string;
  procedure_status: string | null;
  enabled: boolean;
  /** The flow graph changed since the bound procedure was built; re-apply to rebind. */
  stale?: boolean;
  next_run: string | null;
  last_run: string | null;
  activation_required?: string;
  schedule_type?: 'Cron' | 'Interval' | null;
  cron?: string | null;
  interval?: string | null;
  interval_count?: number | null;
  reference_doctype?: string | null;
  doc_event?: string | null;
  condition?: string | null;
}

export type SetFlowTriggerArgs =
  | { flow_id: string; trigger_type: 'schedule'; cron: string }
  | {
      flow_id: string;
      trigger_type: 'doc_event';
      reference_doctype: string;
      doc_event: FlowDocEvent;
      condition?: string;
    };

/** Cron only: an Hourly..Yearly + count interval has no exact 5-field cron and the node schema only holds cron. */
export interface ScheduleForm {
  cron: string;
}

export interface DocEventForm {
  referenceDoctype: string;
  docEvent: FlowDocEvent;
  condition: string;
}

export const DEFAULT_SCHEDULE_FORM: ScheduleForm = { cron: '' };

export const DEFAULT_DOC_EVENT_FORM: DocEventForm = {
  referenceDoctype: '',
  docEvent: 'on_update',
  condition: '',
};

export type ArgsResult<T> = { ok: true; args: T } | { ok: false; error: string };

export function scheduleFormToArgs(flowId: string, form: ScheduleForm): ArgsResult<SetFlowTriggerArgs> {
  const cron = form.cron.trim().replace(/\s+/g, ' ');
  if (!cron || cron.split(' ').length !== 5) {
    return { ok: false, error: 'Cron needs 5 parts: minute hour day month day-of-week.' };
  }
  return { ok: true, args: { flow_id: flowId, trigger_type: 'schedule', cron } };
}

export function docEventFormToArgs(flowId: string, form: DocEventForm): ArgsResult<SetFlowTriggerArgs> {
  if (!form.referenceDoctype.trim()) return { ok: false, error: 'Choose a document type.' };
  const condition = form.condition.trim();
  return {
    ok: true,
    args: {
      flow_id: flowId,
      trigger_type: 'doc_event',
      reference_doctype: form.referenceDoctype.trim(),
      doc_event: form.docEvent,
      ...(condition ? { condition } : {}),
    },
  };
}

export function summaryToScheduleForm(s: FlowTriggerSummary | null): ScheduleForm {
  if (!s || s.trigger_type !== 'Schedule' || s.schedule_type !== 'Cron') return { ...DEFAULT_SCHEDULE_FORM };
  return { cron: s.cron ?? '' };
}

export function summaryToDocEventForm(s: FlowTriggerSummary | null): DocEventForm {
  if (!s || s.trigger_type !== 'Doc Event') return { ...DEFAULT_DOC_EVENT_FORM };
  const event = DOC_EVENTS.find((e) => e === s.doc_event) ?? DEFAULT_DOC_EVENT_FORM.docEvent;
  return {
    referenceDoctype: s.reference_doctype ?? '',
    docEvent: event,
    condition: s.condition ?? '',
  };
}

/**
 * The node config the canvas keeps in step with the saved trigger, so graph validation, activation
 * rules and the node's `configured` flag need no special cases. Only schema-allowed keys
 * (TriggerScheduleNode: cron; TriggerDocEventNode: doctype + event). Null when the server
 * holds no trigger of this kind, or one the node config cannot express (an interval schedule,
 * or a doc event outside DOC_EVENTS).
 */
export function summaryToNodeConfig(
  kind: 'schedule' | 'doc-event',
  s: FlowTriggerSummary | null
): { cron: string } | { doctype: string; event: FlowDocEvent } | null {
  if (!s) return null;
  if (kind === 'schedule') {
    const cron = (s.cron ?? '').trim();
    return s.trigger_type === 'Schedule' && s.schedule_type === 'Cron' && cron ? { cron } : null;
  }
  const event = DOC_EVENTS.find((e) => e === s.doc_event);
  return s.trigger_type === 'Doc Event' && s.reference_doctype && event
    ? { doctype: s.reference_doctype, event }
    : null;
}

/**
 * The triggerConfig a schedule / doc-event node should hold after a sync, replacing whatever it held
 * (legacy keys the schema forbids are dropped). Null when it already matches, to avoid dirtying the flow.
 */
export function syncedTriggerConfig(
  kind: 'schedule' | 'doc-event',
  current: Record<string, unknown>,
  mirror: ReturnType<typeof summaryToNodeConfig>
): Record<string, unknown> | null {
  const next: Record<string, unknown> = { type: kind, ...(mirror ?? {}) };
  const keys = new Set([...Object.keys(current), ...Object.keys(next)]);
  return [...keys].every((k) => current[k] === next[k]) ? null : next;
}

export type TriggerStateKind = 'none' | 'live' | 'disabled' | 'activation_required';

export interface TriggerState {
  kind: TriggerStateKind;
  message: string;
  /** Procedure to link to when the user has to act on it. */
  procedure?: string;
}

/** Only `live` may be shown as firing: the Automation must be Active and the trigger enabled. */
export function describeTriggerState(s: FlowTriggerSummary | null): TriggerState {
  if (!s) return { kind: 'none', message: 'No trigger configured for this flow.' };
  if (s.automation_status !== 'Active') {
    return {
      kind: 'activation_required',
      procedure: s.procedure,
      message:
        s.activation_required ||
        `Procedure ${s.procedure} is ${s.procedure_status ?? 'not enabled'}. Set it to Testing or Active, then retry activation.`,
    };
  }
  if (!s.enabled) return { kind: 'disabled', message: 'Trigger is saved but disabled.', procedure: s.procedure };
  return { kind: 'live', message: 'Live: this trigger will fire.', procedure: s.procedure };
}

export interface TriggerErrorInfo {
  kind: 'not_convertible' | 'other';
  message: string;
}

const NOT_CONVERTIBLE_RE = /cannot take a schedule or doc-event trigger:?\s*(.*)$/is;

/** Turn a thrown API error into an inline message; non-deterministic flows are called out. */
export function triggerErrorInfo(err: unknown): TriggerErrorInfo {
  const raw = (err instanceof Error ? err.message : typeof err === 'string' ? err : '') || '';
  let stripped = raw;
  for (let prev = ''; prev !== stripped; ) {
    prev = stripped;
    stripped = stripped.replace(/<[^>]*>/g, '');
  }
  const text = stripped.trim();
  const m = NOT_CONVERTIBLE_RE.exec(text);
  if (m || /Flow Is Not Convertible/i.test(text)) {
    const reason = (m?.[1] ?? '').trim();
    return {
      kind: 'not_convertible',
      message:
        'This flow cannot take a schedule or doc-event trigger because it is not deterministic' +
        (reason ? `: ${reason}` : '.') +
        ' Remove agent, LLM-router and approval steps to use it.',
    };
  }
  return { kind: 'other', message: text || 'Could not update the trigger.' };
}

/** Why the form is read-only, or null when it can be edited. */
export function triggerDisabledReason(flowId: string | null | undefined, hasUnsavedChanges: boolean): string | null {
  if (!flowId) return 'Save this flow first. A trigger can only be set on a saved flow.';
  if (hasUnsavedChanges) {
    return 'Save your changes first. The trigger runs the saved version of this flow.';
  }
  return null;
}
