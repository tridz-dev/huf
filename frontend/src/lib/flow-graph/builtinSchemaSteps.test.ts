// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import type { Flow, FlowEdge, FlowNode } from '@/types/flow.types';
import { deserializeFlow, makeFlowEdge, serializeFlow } from '@/services/flowSerializer';
import { appActionOptions, findActionOption, getAppNodeType, missingAppStep, setAppNodeTypes } from './appNodeTypes';
import { validateNode } from './flowValidation';
import { actionLabel, actionCardId } from '../flow/flowLabels';

afterEach(() => setAppNodeTypes(null));

const step = (backend_type: string, cfg: Record<string, unknown> = {}) =>
  ({ id: 's', data: { label: 'X', nodeType: 'action', actionConfig: { type: 'unknown', backend_type, ...cfg } } });

describe('knowledge.search and handoff are built-in steps', () => {
  it('are never reported as a missing app, and have titles, forms and palette entries', () => {
    setAppNodeTypes([]);
    for (const [type, title] of [['knowledge.search', 'Search knowledge'], ['handoff', 'Hand to a person']]) {
      expect(missingAppStep(type)).toBeNull();
      expect(getAppNodeType(type)?.label).toBe(title);
      expect(actionLabel(actionCardId({ type: 'unknown', backend_type: type }))).toBe(title);
      expect(findActionOption(type)?.name).toBe(title);
    }
    expect(appActionOptions([]).map((o) => o.id)).toEqual(['knowledge.search', 'handoff']);
    expect(Object.keys(getAppNodeType('handoff')!.config_schema.properties!)).toContain('timeout_next');
  });

  it('asks for the search text and source, and nothing for a handoff', () => {
    setAppNodeTypes([]);
    expect(validateNode(step('knowledge.search'), []).map((i) => i.field).sort()).toEqual(['knowledge_source', 'query']);
    expect(validateNode(step('handoff'), [])).toEqual([]);
  });
});

const node = (id: string, extra: Partial<FlowNode> = {}): FlowNode =>
  ({ id, type: 'action', position: { x: 0, y: 0 }, data: { label: id, nodeType: 'action' }, ...extra } as FlowNode);

describe('router.decision Let AI choose', () => {
  it('saves the paths as candidates and the otherwise path as the unsure path, and loads them back', () => {
    const nodes = [
      node('start', { data: { label: 'Start', nodeType: 'trigger' } as FlowNode['data'] }),
      node('step', { data: { label: 'Choose', nodeType: 'action', actionConfig: { type: 'router-decision', decision: { instructions: 'Pick a team' } } } as unknown as FlowNode['data'] }),
      node('billing'), node('support'), node('review'),
    ];
    const edges: FlowEdge[] = [
      makeFlowEdge('start', 'step', 'next'),
      makeFlowEdge('step', 'billing', 'option', { label: 'Billing', index: 0, expression: '' }),
      makeFlowEdge('step', 'support', 'option', { label: 'Support', index: 1, expression: '' }),
      makeFlowEdge('step', 'review', 'default'),
    ];
    const flow = { id: 'f', name: 'F', status: 'draft', nodes, edges, createdAt: new Date(0), updatedAt: new Date(0), version: 1 } as unknown as Flow;
    const graph = serializeFlow(flow) as unknown as { nodes: Array<{ id: string; config: Record<string, unknown> }> };
    const cfg = graph.nodes.find((n) => n.id === 'step')!.config;
    expect(cfg.decision).toEqual({
      instructions: 'Pick a team',
      candidates: [{ node_id: 'billing', label: 'Billing' }, { node_id: 'support', label: 'Support' }],
      uncertain_next: 'review',
    });
    expect(cfg.options).toEqual([{ label: 'Billing', node_id: 'billing' }, { label: 'Support', node_id: 'support' }]);

    const back = deserializeFlow('f', 'F', 'Draft', graph as never);
    const loaded = back.nodes.find((n) => n.id === 'step')!.data.actionConfig as unknown as Record<string, unknown>;
    expect((loaded.decision as Record<string, unknown>).instructions).toBe('Pick a team');
    const out = back.edges.filter((e) => e.source === 'step');
    expect(validateNode({ id: 'step', data: { label: 'Choose', nodeType: 'action', actionConfig: loaded } } as never, out as never)).toEqual([]);
  });
});
