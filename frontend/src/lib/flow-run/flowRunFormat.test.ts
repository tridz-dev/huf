import { describe, expect, it } from 'vitest';
import { asCodeStepOutput, describeDecision, flowRunStatusLabel, isFailedStepOutput, titleNodeIds, withoutFailureKeys } from './flowRunFormat';
import { parseServerDate, setSiteTimezoneForTests, toServerDatetime } from '../serverTime';

describe('describeDecision', () => {
  it('words an approval with who and when', () => {
    const text = describeDecision({ decision: 'approved', decided_by: 'ana@example.com', decided_at: '2026-10-28T01:45:00Z' });
    expect(text).toMatch(/^Approved by ana@example\.com on /);
  });
  it('words a rejection without a time when none was recorded', () => {
    expect(describeDecision({ decision: 'rejected', decided_by: 'bo@example.com' })).toBe('Rejected by bo@example.com');
  });
  it('words a timeout', () => {
    expect(describeDecision({ decision: 'timeout', comment: null })).toBe('Timed out with no answer');
  });
  it('ignores other step outputs', () => {
    expect(describeDecision({ success: true })).toBeNull();
    expect(describeDecision('x')).toBeNull();
  });
});

describe('server time', () => {
  it('reads naive Frappe datetimes in the site zone', () => {
    setSiteTimezoneForTests('Asia/Kolkata');
    expect(parseServerDate('2026-10-28 07:15:00.123456')?.toISOString()).toBe('2026-10-28T01:45:00.123Z');
    setSiteTimezoneForTests(null);
  });
  it('keeps offset-carrying strings as they are', () => {
    setSiteTimezoneForTests('Asia/Kolkata');
    expect(parseServerDate('2026-10-28T01:45:00Z')?.toISOString()).toBe('2026-10-28T01:45:00.000Z');
    setSiteTimezoneForTests(null);
  });
  it('formats a Date as naive site time for filters', () => {
    setSiteTimezoneForTests('Asia/Kolkata');
    expect(toServerDatetime(new Date('2026-10-28T01:45:00Z'))).toBe('2026-10-28 07:15:00');
    setSiteTimezoneForTests(null);
  });
  it('handles a DST zone', () => {
    setSiteTimezoneForTests('America/New_York');
    expect(parseServerDate('2026-07-01 12:00:00')?.toISOString()).toBe('2026-07-01T16:00:00.000Z');
    expect(parseServerDate('2026-12-01 12:00:00')?.toISOString()).toBe('2026-12-01T17:00:00.000Z');
    setSiteTimezoneForTests(null);
  });
});

describe('titleNodeIds', () => {
    const titles: Record<string, string> = { n2: 'Send the email', n3: 'Escalate' };
    const titleOf = (id: string) => titles[id] ?? null;

    it('shows step titles for router, condition and approval targets', () => {
        expect(titleNodeIds({ label: 'billing', node_id: 'n2', reason: 'matched' }, titleOf)).toEqual({
            label: 'billing',
            node_id: 'Send the email',
            reason: 'matched',
        });
        expect(titleNodeIds({ on_true: 'n2', on_false: 'n3', timeout_next: 'n3' }, titleOf)).toEqual({
            on_true: 'Send the email',
            on_false: 'Escalate',
            timeout_next: 'Escalate',
        });
    });

    it('leaves unknown ids and unrelated keys alone', () => {
        expect(titleNodeIds({ node_id: 'zz', other: 'n2', nested: [{ next: 'n3' }] }, titleOf)).toEqual({
            node_id: 'zz',
            other: 'n2',
            nested: [{ next: 'n3' }],
        });
    });

    it('never touches free text nested in the data, even when it looks like a step id', () => {
        const data = { input: { target: 'n2', next: 'n3' }, items: [{ node_id: 'n2' }] };
        expect(titleNodeIds(data, titleOf)).toEqual(data);
    });

    it('only changes a value that is a known step id (a title that equals its id changes nothing)', () => {
        const same = (id: string) => (id === 'n2' ? 'n2' : null);
        expect(titleNodeIds({ node_id: 'n2', next: 'Send the email' }, same)).toEqual({ node_id: 'n2', next: 'Send the email' });
    });
});

describe('failed step output', () => {
    it('treats status failed with an error as failed, even when the run went on', () => {
        expect(isFailedStepOutput({ status: 'failed', error: 'boom' })).toBe(true);
        expect(isFailedStepOutput({ success: false })).toBe(true);
        expect(isFailedStepOutput({ status: 'success', value: 1 })).toBe(false);
        expect(isFailedStepOutput('text')).toBe(false);
        expect(isFailedStepOutput(null)).toBe(false);
    });

    it('drops the status and error keys already shown as the reason', () => {
        expect(withoutFailureKeys({ status: 'failed', error: 'boom', status_code: 500 })).toEqual({ status_code: 500 });
        expect(withoutFailureKeys({ success: false, error: 'boom' })).toEqual({});
    });
});

describe('Execute code step output', () => {
    it('reads stdout, result, exit status and truncation', () => {
        expect(asCodeStepOutput({ stdout: 'hi\n', result: { n: 2 }, exit_status: 'Ok', truncated: false })).toEqual({
            stdout: 'hi\n', result: { n: 2 }, exitStatus: 'Ok', truncated: false,
        });
        expect(asCodeStepOutput({ status: 'failed', error: 'x', exit_status: 'Timeout', truncated: true })).toMatchObject({ exitStatus: 'Timeout', stdout: '', truncated: true });
    });

    it('is null for any other step output', () => {
        expect(asCodeStepOutput({ result: 1 })).toBeNull();
        expect(asCodeStepOutput('text')).toBeNull();
        expect(asCodeStepOutput(null)).toBeNull();
    });

    it('words the Waiting Code status', () => {
        expect(flowRunStatusLabel('Waiting Code')).toBe('Waiting for code');
        expect(flowRunStatusLabel('Waiting Approval')).toBe('Waiting Approval');
    });
});
