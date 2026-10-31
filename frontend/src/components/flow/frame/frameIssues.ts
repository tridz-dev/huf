import type { FlowIssue } from '@/lib/flow-graph/flowValidation';

/** The three tabs of a step's panel. Triggers have Setup and Test; End has Setup only. */
export type FrameTab = 'setup' | 'test' | 'settings';

/** Triggers: Setup + Test. End: Setup only. Everything else: all three. */
export function tabsFor(node: { data: { nodeType?: string } }): FrameTab[] {
  if (node.data.nodeType === 'end') return ['setup'];
  if (node.data.nodeType === 'trigger') return ['setup', 'test'];
  return ['setup', 'test', 'settings'];
}

/** Fields that live in the Settings tab. Every other field, and every required one, is in Setup. */
const SETTINGS_FIELDS = new Set(['timeout_ms']);

export function issueTab(issue: Pick<FlowIssue, 'field'>): FrameTab {
  return SETTINGS_FIELDS.has(issue.field) ? 'settings' : 'setup';
}

export function issuesForStep(issues: FlowIssue[], nodeId: string): FlowIssue[] {
  return issues.filter((i) => i.nodeId === nodeId);
}

/** Distinct steps that have something to finish (flow-level issues such as "no trigger" count once each). */
export function stepsToFinish(issues: FlowIssue[]): number {
  const steps = new Set(issues.filter((i) => i.nodeId).map((i) => i.nodeId));
  return steps.size + issues.filter((i) => !i.nodeId).length;
}

/** Header words: "3 steps to finish", "1 step to finish", or "1 thing to finish" when the flow itself lacks something. */
export function finishText(issues: FlowIssue[]): string {
  const n = stepsToFinish(issues);
  if (n === 0) return '';
  const flowLevel = issues.some((i) => !i.nodeId);
  const noun = flowLevel ? 'thing' : 'step';
  return `${n} ${noun}${n === 1 ? '' : 's'} to finish`;
}

/** Strip words inside one step: "2 things to finish" or "Ready". */
export function stripText(count: number): string {
  return count === 0 ? 'Ready' : `${count} thing${count === 1 ? '' : 's'} to finish`;
}

/** Group a flow's issues by step, in the order the steps first appear. */
export function groupByStep(issues: FlowIssue[]): Array<{ nodeId: string; label: string; issues: FlowIssue[] }> {
  const out: Array<{ nodeId: string; label: string; issues: FlowIssue[] }> = [];
  for (const issue of issues) {
    let group = out.find((g) => g.nodeId === issue.nodeId);
    if (!group) {
      group = { nodeId: issue.nodeId, label: issue.nodeLabel, issues: [] };
      out.push(group);
    }
    group.issues.push(issue);
  }
  return out;
}

/** Selector of the control for a field, by the test id every form already gives it (`flow-field-<kind>-<field>`). */
export function fieldSelector(kind: string, field: string): string {
  return `[data-testid="flow-field-${kind}-${field}"]`;
}
