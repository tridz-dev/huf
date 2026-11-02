import { describe, expect, it } from 'vitest';
import { runCanStillChange } from './runCanStillChange';
import { overlayFromRun } from './story/overlay';
import type { FlowRunDetail } from '@/services/flowApi';

describe('runCanStillChange', () => {
  it('keeps refreshing while a run is queued, running or waiting for anyone', () => {
    for (const s of ['Queued', 'Running', 'Waiting Code', 'Waiting Approval', 'Waiting User']) expect(runCanStillChange(s)).toBe(true);
  });
  it('stops once the run ended or is unknown', () => {
    for (const s of ['Success', 'Failed', 'Stopped', 'Cancelled', '', null, undefined]) expect(runCanStillChange(s)).toBe(false);
  });
});

describe('a rejected approval run', () => {
  const run = (status: string, outputs: Record<string, unknown>) =>
    ({ status, current_node_id: 'wait', context_json: { __node_outputs__: outputs }, step_meta: { wait: { type: 'human.approval' } }, waiting: { type: 'approval' } }) as unknown as FlowRunDetail;
  it('shows the approval step as waiting while parked, done once the run finished', () => {
    expect(overlayFromRun(run('Waiting Approval', {})).wait.status).toBe('waiting');
    expect(overlayFromRun(run('Success', { wait: { decision: 'rejected' } })).wait.status).toBe('done');
  });
});
