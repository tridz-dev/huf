import { describe, it, expect } from 'vitest';
import {
  summaryToNodeConfig,
  syncedTriggerConfig,
  DOC_EVENTS,
  scheduleFormToArgs,
  docEventFormToArgs,
  summaryToScheduleForm,
  summaryToDocEventForm,
  describeTriggerState,
  triggerErrorInfo,
  triggerDisabledReason,
  DEFAULT_SCHEDULE_FORM,
  type FlowTriggerSummary,
} from './flowTrigger';

const base: FlowTriggerSummary = {
  flow_id: 'f1',
  trigger_type: 'Schedule',
  automation: 'Flow Trigger: f1',
  automation_trigger: 't1',
  automation_status: 'Active',
  procedure: 'f1-procedure-1',
  procedure_status: 'Testing',
  enabled: true,
  next_run: '2026-01-01 10:00:00',
  last_run: null,
};

describe('scheduleFormToArgs', () => {
  it('normalises whitespace', () => {
    const r = scheduleFormToArgs('f1', { cron: ' 0  */6 * * * ' });
    expect(r).toEqual({ ok: true, args: { flow_id: 'f1', trigger_type: 'schedule', cron: '0 */6 * * *' } });
  });
  it('rejects non 5-part cron and empty input', () => {
    expect(scheduleFormToArgs('f1', { cron: '* * *' }).ok).toBe(false);
    expect(scheduleFormToArgs('f1', DEFAULT_SCHEDULE_FORM).ok).toBe(false);
  });
});

describe('docEventFormToArgs', () => {
  it('requires a doctype', () => {
    expect(docEventFormToArgs('f1', { referenceDoctype: ' ', docEvent: 'on_update', condition: '' }).ok).toBe(false);
  });
  it('omits empty condition', () => {
    const r = docEventFormToArgs('f1', { referenceDoctype: 'ToDo', docEvent: 'on_update', condition: ' ' });
    expect(r).toEqual({
      ok: true,
      args: { flow_id: 'f1', trigger_type: 'doc_event', reference_doctype: 'ToDo', doc_event: 'on_update' },
    });
  });
});

describe('hydration', () => {
  it('does not hydrate interval schedules into the cron-only form', () => {
    expect(summaryToScheduleForm({ ...base, schedule_type: 'Interval', interval: 'Monthly', interval_count: 3 })).toEqual(DEFAULT_SCHEDULE_FORM);
  });
  it('round-trips cron schedules', () => {
    expect(summaryToScheduleForm({ ...base, schedule_type: 'Cron', cron: '5 4 * * *' })).toEqual({ cron: '5 4 * * *' });
  });
  it('falls back to defaults for other trigger types or none', () => {
    expect(summaryToScheduleForm(null)).toEqual(DEFAULT_SCHEDULE_FORM);
    expect(summaryToDocEventForm({ ...base }).referenceDoctype).toBe('');
  });
  it('hydrates doc events', () => {
    const f = summaryToDocEventForm({
      ...base,
      trigger_type: 'Doc Event',
      reference_doctype: 'ToDo',
      doc_event: 'on_submit',
      condition: 'doc.x',
    });
    expect(f).toEqual({ referenceDoctype: 'ToDo', docEvent: 'on_submit', condition: 'doc.x' });
  });
});

describe('describeTriggerState', () => {
  it('is live only when Active and enabled', () => {
    expect(describeTriggerState(base).kind).toBe('live');
    expect(describeTriggerState({ ...base, enabled: false }).kind).toBe('disabled');
  });
  it('never claims live for a Draft automation', () => {
    const s = describeTriggerState({
      ...base,
      automation_status: 'Draft',
      enabled: false,
      procedure_status: 'Draft',
      activation_required: 'Procedure p is Draft.',
    });
    expect(s).toMatchObject({ kind: 'activation_required', procedure: 'f1-procedure-1', message: 'Procedure p is Draft.' });
  });
  it('handles no trigger', () => {
    expect(describeTriggerState(null).kind).toBe('none');
  });
});

describe('triggerErrorInfo', () => {
  it('flags non-deterministic flows', () => {
    const e = triggerErrorInfo(new Error("Flow 'f1' cannot take a schedule or doc-event trigger: contains agent.run"));
    expect(e.kind).toBe('not_convertible');
    expect(e.message).toContain('contains agent.run');
  });
  it('passes other messages through, stripped of html', () => {
    expect(triggerErrorInfo(new Error('<b>Not permitted</b>'))).toEqual({ kind: 'other', message: 'Not permitted' });
  });
});

describe('triggerDisabledReason', () => {
  it('explains unsaved flows and dirty graphs', () => {
    expect(triggerDisabledReason(null, false)).toMatch(/Save this flow/);
    expect(triggerDisabledReason('f1', true)).toMatch(/Save your changes/);
    expect(triggerDisabledReason('f1', false)).toBeNull();
  });
});

describe('summaryToNodeConfig', () => {
  it('mirrors a cron schedule as { cron } only', () => {
    expect(summaryToNodeConfig('schedule', { ...base, schedule_type: 'Cron', cron: ' 5 4 * * * ' })).toEqual({ cron: '5 4 * * *' });
  });
  it('has nothing for interval schedules, other kinds, or no trigger', () => {
    expect(summaryToNodeConfig('schedule', { ...base, schedule_type: 'Interval', interval: 'Daily', interval_count: 1 })).toBeNull();
    expect(summaryToNodeConfig('doc-event', { ...base, schedule_type: 'Cron', cron: '5 4 * * *' })).toBeNull();
    expect(summaryToNodeConfig('schedule', null)).toBeNull();
  });
  it('mirrors a doc event as { doctype, event } only for schema-enum events', () => {
    const doc = { ...base, trigger_type: 'Doc Event' as const, reference_doctype: 'ToDo', doc_event: 'on_update' };
    expect(summaryToNodeConfig('doc-event', doc)).toEqual({ doctype: 'ToDo', event: 'on_update' });
    expect(summaryToNodeConfig('doc-event', { ...doc, doc_event: 'before_save' })).toBeNull();
  });
  it('the offered events are all inside the graph IR enum', () => {
    // Mirrors graph_ir.schema.json TriggerDocEventNode.config.event (ajv is not a direct frontend dependency).
    expect([...DOC_EVENTS]).toEqual(['after_insert', 'on_update', 'on_submit', 'on_cancel', 'on_trash']);
  });
});

describe('syncedTriggerConfig', () => {
  it('drops legacy keys and returns null when already in step', () => {
    expect(syncedTriggerConfig('schedule', { type: 'schedule', intervalType: 'hours', interval: 1 }, { cron: '0 * * * *' })).toEqual({ type: 'schedule', cron: '0 * * * *' });
    expect(syncedTriggerConfig('schedule', { type: 'schedule', cron: '0 * * * *' }, { cron: '0 * * * *' })).toBeNull();
    expect(syncedTriggerConfig('doc-event', { type: 'doc-event', doctype: 'ToDo', event: 'on_update' }, null)).toEqual({ type: 'doc-event' });
  });
});
