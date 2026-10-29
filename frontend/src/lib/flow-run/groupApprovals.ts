import type { PendingApproval } from '@/services/flowApi';

export interface ApprovalGroup {
  key: string;
  flowName: string;
  /** The request in words (same text for every item in the group). */
  sentence: string;
  items: PendingApproval[];
}

/**
 * Groups waiting approvals that are the same request (same flow, same words), newest first inside each group, groups in the
 * order of their newest item. Three identical "Approve the order?" requests read as one line, "3 waiting: Order approval".
 */
export function groupApprovals(approvals: PendingApproval[], sentenceOf: (a: PendingApproval) => string): ApprovalGroup[] {
  const groups = new Map<string, ApprovalGroup>();
  for (const approval of approvals) {
    const sentence = sentenceOf(approval);
    const key = `${approval.flow_id}|${sentence}`;
    const group = groups.get(key);
    if (group) group.items.push(approval);
    else groups.set(key, { key, flowName: approval.flow_name || approval.flow_id, sentence, items: [approval] });
  }
  return [...groups.values()];
}

/** "3 waiting: Order approval" for a group of several, null for a lone request. */
export function groupHeading(group: ApprovalGroup): string | null {
  return group.items.length > 1 ? `${group.items.length} waiting: ${group.flowName}` : null;
}
