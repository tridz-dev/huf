import { describe, expect, it } from 'vitest';
import type { Edge, Node } from 'reactflow';
import type { FlowNodeData } from '@/types/flow.types';
import { orderSteps } from './stepsOrder';

const node = (id: string, nodeType: FlowNodeData['nodeType']): Node<FlowNodeData> => ({ id, position: { x: 0, y: 0 }, data: { label: id, nodeType } as FlowNodeData });
const edge = (source: string, target: string, route?: string): Edge => ({ id: `${source}-${target}`, source, target, data: route ? { route } : undefined });

describe('orderSteps', () => {
  it('walks a straight flow from the trigger', () => {
    const steps = orderSteps([node('c', 'end'), node('a', 'trigger'), node('b', 'action')], [edge('a', 'b'), edge('b', 'c')]);
    expect(steps.map((s) => s.id)).toEqual(['a', 'b', 'c']);
    expect(steps.every((s) => s.depth === 0 && s.branch === null)).toBe(true);
  });
  it('lists each branch after its split with its name', () => {
    const steps = orderSteps(
      [node('t', 'trigger'), node('if', 'action'), node('big', 'action'), node('small', 'action')],
      [edge('t', 'if'), edge('if', 'big', 'true'), edge('if', 'small', 'false')],
    );
    expect(steps.map((s) => [s.id, s.depth, s.branch])).toEqual([['t', 0, null], ['if', 0, null], ['big', 1, 'Yes'], ['small', 1, 'No']]);
  });
  it('puts steps nothing leads to last and never repeats a step', () => {
    const steps = orderSteps([node('t', 'trigger'), node('x', 'action'), node('y', 'action')], [edge('t', 'y'), edge('y', 't')]);
    expect(steps.map((s) => s.id)).toEqual(['t', 'y', 'x']);
  });
});
