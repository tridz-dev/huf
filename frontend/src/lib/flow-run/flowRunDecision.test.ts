import { describe, expect, it } from 'vitest';
import { decisionMovedRun } from './flowRunDecision';

describe('decisionMovedRun', () => {
  it('accepts a run that left Waiting Approval', () => {
    expect(decisionMovedRun({ status: 'Success', current_node_id: 'b' }, 'a')).toBe(true);
    expect(decisionMovedRun({ status: 'Running', current_node_id: 'b' }, 'a')).toBe(true);
    expect(decisionMovedRun({ status: 'Failed', current_node_id: 'a' }, 'a')).toBe(true);
  });
  it('accepts a run now waiting at a later approval step', () => {
    expect(decisionMovedRun({ status: 'Waiting Approval', current_node_id: 'c' }, 'a')).toBe(true);
  });
  it('refuses an answer that still shows the run waiting at the step that was decided', () => {
    expect(decisionMovedRun({ status: 'Waiting Approval', current_node_id: 'a' }, 'a')).toBe(false);
  });
  it('refuses an empty or unreadable answer', () => {
    expect(decisionMovedRun(undefined, 'a')).toBe(false);
    expect(decisionMovedRun({}, 'a')).toBe(false);
    expect(decisionMovedRun({ status: 'Waiting Approval' }, 'a')).toBe(false);
  });
});
