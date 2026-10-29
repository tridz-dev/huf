// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { FlowIssue } from '@/lib/flow-graph/flowValidation';
import { fieldSelector, finishText, groupByStep, issueTab, issuesForStep, stepsToFinish, stripText, tabsFor } from './frameIssues';
import { canDisableStep, canDuplicateStep, duplicateStep } from './stepActions';
import type { FlowNode } from '../../../types/flow.types';

const issue = (nodeId: string, field: string, message = `fix ${field}`): FlowIssue => ({ nodeId, nodeLabel: `Step ${nodeId}`, kind: 'agent.run', field, message });
const node = (data: Partial<FlowNode['data']>): FlowNode => ({ id: 'n1', type: 'x', position: { x: 10, y: 20 }, data: { label: 'Send email', nodeType: 'action', configured: true, ...data } }) as FlowNode;

describe('step panel issues', () => {
  it('counts steps, not fields, for the header', () => {
    const list = [issue('a', 'agent'), issue('a', 'prompt'), issue('b', 'prompt')];
    expect(stepsToFinish(list)).toBe(2);
    expect(finishText(list)).toBe('2 steps to finish');
    expect(finishText([issue('a', 'agent')])).toBe('1 step to finish');
    expect(finishText([])).toBe('');
  });

  it('says "things" when the flow itself lacks something', () => {
    const flowLevel: FlowIssue = { nodeId: '', nodeLabel: 'Flow', kind: 'flow', field: 'trigger', message: 'Add a trigger' };
    expect(finishText([flowLevel])).toBe('1 thing to finish');
    expect(finishText([flowLevel, issue('a', 'agent')])).toBe('2 things to finish');
  });

  it('strip words: Ready or N things', () => {
    expect(stripText(0)).toBe('Ready');
    expect(stripText(1)).toBe('1 thing to finish');
    expect(stripText(2)).toBe('2 things to finish');
  });

  it('a required field is in Setup; only optional time limits are in Settings', () => {
    expect(issueTab(issue('a', 'agent'))).toBe('setup');
    expect(issueTab(issue('a', 'approver_role'))).toBe('setup');
    expect(issueTab(issue('a', 'branch.true'))).toBe('setup');
    expect(issueTab(issue('a', 'timeout_ms'))).toBe('settings');
  });

  it('groups by step in order and filters one step', () => {
    const list = [issue('b', 'x'), issue('a', 'y'), issue('b', 'z')];
    expect(groupByStep(list).map((g) => [g.nodeId, g.issues.length])).toEqual([['b', 2], ['a', 1]]);
    expect(issuesForStep(list, 'b')).toHaveLength(2);
  });

  it('finds a control by the test id every form gives it', () => {
    expect(fieldSelector('agent.run', 'input.to')).toBe('[data-testid="flow-field-agent.run-input.to"]');
  });
});

describe('panel tabs', () => {
  it('triggers have Setup and Test, End has Setup only, steps have all three', () => {
    expect(tabsFor(node({ nodeType: 'trigger' }))).toEqual(['setup', 'test']);
    expect(tabsFor(node({ nodeType: 'end' }))).toEqual(['setup']);
    expect(tabsFor(node({ nodeType: 'action' }))).toEqual(['setup', 'test', 'settings']);
  });
});

describe('step menu', () => {
  it('duplicates a step next to the original, unconnected, without sharing data', () => {
    const original = node({ actionConfig: { type: 'tool-call', tool_id: 'gmail_send_email', input: { to: 'a@b.co' } } });
    const copy = duplicateStep(original, 123);
    expect(copy.id).toBe('node_123');
    expect(copy.data.label).toBe('Send email copy');
    expect(copy.position).toEqual({ x: 58, y: 92 });
    (copy.data.actionConfig as { input: Record<string, string> }).input.to = 'changed';
    expect((original.data.actionConfig as { input: Record<string, string> }).input.to).toBe('a@b.co');
  });

  it('only linear action steps can be turned off; triggers cannot be duplicated', () => {
    expect(canDisableStep(node({ actionConfig: { type: 'tool-call' } }))).toBe(true);
    expect(canDisableStep(node({ actionConfig: { type: 'condition' } }))).toBe(false);
    expect(canDisableStep(node({ actionConfig: { type: 'human.approval' } }))).toBe(false);
    expect(canDisableStep(node({ nodeType: 'end' }))).toBe(false);
    expect(canDuplicateStep(node({ nodeType: 'trigger' }))).toBe(false);
    expect(canDuplicateStep(node({ nodeType: 'end' }))).toBe(true);
  });
});
