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
  it('groups by flow wherever the rows sit, keeping each row its own words when they differ', () => {
    const words = new Map([['a', 'x'], ['b', 'y'], ['c', 'x'], ['d', 'x']]);
    const groups = groupApprovals(
      [item('a'), item('d', 'refund', 'Refunds'), item('b'), item('c')],
      (i) => words.get(i.flow_run_id) ?? 'x',
    );
    expect(groups.map((g) => g.items.map((i) => i.flow_run_id))).toEqual([['a', 'b', 'c'], ['d']]);
    expect(groups[0].sentence).toBe('');
    expect(groups[0].sentences).toEqual(['x', 'y', 'x']);
    expect(groupHeading(groups[0])).toBe('3 waiting: Order approval');
    expect(groupHeading(groups[1])).toBeNull();
  });
  it('keeps flows apart even with the same words and time', () => {
    const groups = groupApprovals([item('a'), item('b', 'refund', 'Refunds')], () => 'Approve?');
    expect(groups).toHaveLength(2);
  });
});
