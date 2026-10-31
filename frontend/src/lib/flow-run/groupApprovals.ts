import type { PendingApproval } from '@/services/flowApi';

export interface ApprovalGroup {
  key: string;
  flowName: string;
  /** The request in words when every item in the group says the same, otherwise ''. */
  sentence: string;
  /** Each item's own words, in item order (used when the items differ). */
  sentences: string[];
  items: PendingApproval[];
}

/**
 * Groups every waiting approval of the same flow into one block, wherever the rows sit in the list, so the list reads the same on
 * a phone and on a desktop: "3 waiting: Order approval". When the requests of a flow use the same words the sentence is shown once
 * (`sentence`); when they differ each row keeps its own words (`sentenceOf`). Groups keep the order of their first item.
 */
export function groupApprovals(approvals: PendingApproval[], sentenceOf: (a: PendingApproval) => string): ApprovalGroup[] {
  const groups = new Map<string, ApprovalGroup>();
  for (const approval of approvals) {
    const sentence = sentenceOf(approval);
    const key = approval.flow_id;
    const group = groups.get(key);
    if (group) {
      group.items.push(approval);
      group.sentences.push(sentence);
      if (group.sentence !== sentence) group.sentence = '';
    } else {
      groups.set(key, { key, flowName: approval.flow_name || approval.flow_id, sentence, sentences: [sentence], items: [approval] });
    }
  }
  return [...groups.values()];
}

/** "3 waiting: Order approval" for a group of several, null for a lone request. */
export function groupHeading(group: ApprovalGroup): string | null {
  return group.items.length > 1 ? `${group.items.length} waiting: ${group.flowName}` : null;
}
