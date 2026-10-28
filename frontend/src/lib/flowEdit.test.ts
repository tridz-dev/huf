import { describe, it, expect } from 'vitest';
import { connectionProblem, removeStep, unreachableNodeIds } from './flowEdit';
import { edgeRoute, makeFlowEdge } from '../services/flowSerializer';
import type { FlowEdge, FlowNode } from '../types/flow.types';

const node = (id: string, nodeType: 'trigger' | 'action' | 'end' = 'action', actionConfig?: Record<string, unknown>): FlowNode =>
  ({ id, type: nodeType, position: { x: 0, y: 0 }, data: { label: id, nodeType, configured: true, actionConfig: actionConfig as never } }) as FlowNode;
const e = (s: string, t: string, route: 'next' | 'true' | 'false' | 'option' = 'next', label?: string): FlowEdge => makeFlowEdge(s, t, route, { label });

describe('removeStep reconnect', () => {
  it('joins the previous step to the next one in a linear chain', () => {
    const g = { nodes: [node('t', 'trigger'), node('a'), node('b'), node('c')], edges: [e('t', 'a'), e('a', 'b'), e('b', 'c')] };
    const out = removeStep(g, 'b', 'reconnect');
    expect(out.nodes.map((n) => n.id)).toEqual(['t', 'a', 'c']);
    expect(out.edges.map((x) => `${x.source}>${x.target}`)).toEqual(['t>a', 'a>c']);
  });
  it('keeps the branch route and the router path name of the step that led in', () => {
    const g = {
      nodes: [node('t', 'trigger'), node('c', 'action', { type: 'condition' }), node('b'), node('d')],
      edges: [e('t', 'c'), e('c', 'b', 'true'), e('b', 'd')],
    };
    const out = removeStep(g, 'b', 'reconnect');
    expect(out.edges.find((x) => x.target === 'd')).toMatchObject({ source: 'c' });
    expect(edgeRoute(out.edges.find((x) => x.target === 'd') as FlowEdge)).toBe('true');
    const r = {
      nodes: [node('t', 'trigger'), node('r', 'action', { type: 'router', default: 'b' }), node('b'), node('d')],
      edges: [e('t', 'r'), e('r', 'b', 'option', 'Billing'), e('b', 'd')],
    };
    const out2 = removeStep(r, 'b', 'reconnect');
    const bridged = out2.edges.find((x) => x.target === 'd') as FlowEdge;
    expect(edgeRoute(bridged)).toBe('option');
    expect(bridged.label).toBe('Billing');
    expect((out2.nodes.find((n) => n.id === 'r')?.data.actionConfig as { default: string }).default).toBe('d');
  });
  it('just removes a last step and leaves branching steps unconnected', () => {
    const g = { nodes: [node('t', 'trigger'), node('a'), node('b')], edges: [e('t', 'a'), e('a', 'b')] };
    expect(removeStep(g, 'b', 'reconnect').edges.map((x) => x.id)).toEqual([e('t', 'a').id]);
    const br = { nodes: [node('t', 'trigger'), node('c', 'action', { type: 'condition' }), node('x'), node('y')], edges: [e('t', 'c'), e('c', 'x', 'true'), e('c', 'y', 'false')] };
    const out = removeStep(br, 'c', 'reconnect');
    expect(out.edges).toEqual([]);
    expect(unreachableNodeIds(out.nodes, out.edges)).toEqual(new Set(['x', 'y']));
  });
});

describe('removeStep cascade', () => {
  it('removes the step and what only it led to, but keeps shared steps', () => {
    const g = {
      nodes: [node('t', 'trigger'), node('c', 'action', { type: 'condition' }), node('a'), node('b'), node('shared'), node('end', 'end')],
      edges: [e('t', 'c'), e('c', 'a', 'true'), e('c', 'shared', 'false'), e('a', 'b'), e('b', 'shared'), e('shared', 'end')],
    };
    const out = removeStep(g, 'a', 'cascade');
    expect(out.nodes.map((n) => n.id).sort()).toEqual(['c', 'end', 'shared', 't']);
    expect(out.edges.map((x) => `${x.source}>${x.target}`).sort()).toEqual(['c>shared', 'shared>end', 't>c']);
  });
});

describe('connectionProblem', () => {
  const g = {
    nodes: [node('t', 'trigger'), node('a'), node('b'), node('end', 'end'), node('c', 'action', { type: 'condition' })],
    edges: [e('t', 'a'), e('a', 'b')],
  };
  it('refuses loops, self links, links into a trigger and out of an End', () => {
    expect(connectionProblem(g, { source: 'b', target: 'a', route: 'next' })).toMatch(/earlier step/);
    expect(connectionProblem(g, { source: 'a', target: 'a', route: 'next' })).toMatch(/itself/);
    expect(connectionProblem(g, { source: 'a', target: 't', route: 'next' })).toMatch(/trigger/);
    expect(connectionProblem(g, { source: 'end', target: 'a', route: 'next' })).toMatch(/ends the flow/);
    expect(connectionProblem(g, { source: 'a', target: 'b', route: 'next' })).toMatch(/already connected/);
  });
  it('refuses a connection point the step does not have', () => {
    expect(connectionProblem(g, { source: 'a', target: 'end', route: 'true' })).toMatch(/connection point/);
    expect(connectionProblem(g, { source: 'c', target: 'end', route: 'next' })).toMatch(/connection point/);
  });
  it('allows a normal connection', () => {
    expect(connectionProblem(g, { source: 'c', target: 'end', route: 'true' })).toBeNull();
    expect(connectionProblem(g, { source: 'a', target: 'end', route: 'next' })).toBeNull();
  });
});

describe('routing fields follow edge removal', () => {
  it('drops on_true from a condition when its True edge is removed, keeps on_false', async () => {
    const { serializeFlow } = await import('../services/flowSerializer');
    const nodes = [node('t', 'trigger'), node('c', 'action', { type: 'condition', expression: 'x' }), node('a'), node('b')];
    (nodes[0].data as { triggerConfig?: unknown }).triggerConfig = { type: 'webhook', method: 'POST', secret: 'abcdefgh1234' };
    const mk = (edges: FlowEdge[]) => serializeFlow({ id: 'f', name: 'f', status: 'draft', nodes, edges, createdAt: new Date(), updatedAt: new Date(), version: 1 });
    const cond = (g: ReturnType<typeof mk>) => g.nodes.find((n) => n.id === 'c')?.config as Record<string, unknown>;
    const full = [e('t', 'c'), e('c', 'a', 'true'), e('c', 'b', 'false')];
    expect(cond(mk(full))).toMatchObject({ on_true: 'a', on_false: 'b' });
    const without = cond(mk(full.filter((x) => x.target !== 'a')));
    expect(without.on_true).toBeUndefined();
    expect(without.on_false).toBe('b');
  });
});
