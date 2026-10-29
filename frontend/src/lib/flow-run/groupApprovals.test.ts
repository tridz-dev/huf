import { describe, expect, it } from 'vitest';
import type { PendingApproval } from '@/services/flowApi';
import { groupApprovals, groupHeading } from './groupApprovals';

const item = (run: string, flow = 'order', name = 'Order approval'): PendingApproval =>
  ({ flow_run_id: run, flow_id: flow, flow_name: name, current_node_id: 'n', title: '', instructions: '', approval_type: 'role', started_at: null, waiting_since: null, view_link: '' }) as PendingApproval;

describe('groupApprovals', () => {
  it('collapses identical requests into one group', () => {
    const groups = groupApprovals([item('a'), item('b'), item('c')], () => 'Approve the order?');
    expect(groups).toHaveLength(1);
    expect(groups[0].items.map((i) => i.flow_run_id)).toEqual(['a', 'b', 'c']);
    expect(groupHeading(groups[0])).toBe('3 waiting: Order approval');
  });
  it('keeps different wording or flows apart', () => {
    const words = new Map([['a', 'x'], ['b', 'y'], ['c', 'x']]);
    const groups = groupApprovals([item('a'), item('b'), item('c', 'refund', 'Refunds')], (i) => words.get(i.flow_run_id) ?? 'x');
    expect(groups.map((g) => g.items.length)).toEqual([1, 1, 1]);
    expect(groupHeading(groups[0])).toBeNull();
  });
});
