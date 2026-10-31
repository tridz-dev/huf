import { describe, expect, it } from 'vitest';
import type { Edge, Node } from 'reactflow';
import { MIN_CARD_GAP, addActionStep, branchPillText, computeOpenEnds, endSubtitles, ghostSpots, loopBacks, orphanNote } from './flowCanvasGraph';
import { edgeRoute, makeFlowEdge } from '../../services/flowSerializer';
import { CARD_WIDTH, ROW_GAP } from '../flow/flowLayout';
import type { FlowNodeData } from '../../types/flow.types';

const node = (id: string, x: number, y: number, type: 'trigger' | 'action' | 'end', cfg?: Record<string, unknown>): Node<FlowNodeData> => ({
  id,
  position: { x, y },
  data: { label: id, nodeType: type, configured: true, actionConfig: cfg as never },
});
const edges = (...e: Array<[string, string, Parameters<typeof makeFlowEdge>[2]]>): Edge[] => e.map(([s, t, r]) => makeFlowEdge(s, t, r) as Edge);

const loopFlow = () => {
  const nodes = [node('t', 0, 0, 'trigger'), node('loop', 0, 150, 'action', { type: 'foreach' }), node('body', 0, 300, 'action', { type: 'agent-run' }), node('done', 290, 300, 'end')];
  return { nodes, edges: edges(['t', 'loop', 'next'], ['loop', 'body', 'body'], ['loop', 'done', 'next']) };
};

describe('loops', () => {
  it('returns the last step of the body to the loop instead of offering an Add step card', () => {
    const { nodes, edges: ed } = loopFlow();
    const ends = computeOpenEnds(nodes, ed);
    expect(loopBacks(nodes, ed, ends)).toEqual([{ leafId: 'body', loopId: 'loop' }]);
    expect(ghostSpots(nodes, ends, ed, null)).toEqual([]);
  });

  it('keeps "For each item" and "When done" on separate handles', () => {
    const { nodes } = loopFlow();
    const ends = computeOpenEnds(nodes, []);
    expect(new Set(ends.filter((e) => e.nodeId === 'loop').map((e) => e.handleId)).size).toBe(2);
  });

  it('shows the optional "When done" card only while the loop is selected', () => {
    const nodes = [node('t', 0, 0, 'trigger'), node('loop', 0, 150, 'action', { type: 'foreach' }), node('body', -145, 300, 'action', { type: 'agent-run' })];
    const ed = edges(['t', 'loop', 'next'], ['loop', 'body', 'body']);
    const ends = computeOpenEnds(nodes, ed);
    expect(ghostSpots(nodes, ends, ed, null).map((g) => g.end.route)).toEqual([]);
    expect(ghostSpots(nodes, ends, ed, 'loop').map((g) => g.end.route)).toEqual(['next']);
  });
});

describe('ghost cards', () => {
  it('puts the cards of one step a full column apart', () => {
    const nodes = [node('t', 0, 0, 'trigger'), node('c', 0, 150, 'action', { type: 'condition' })];
    const ed = edges(['t', 'c', 'next']);
    const spots = ghostSpots(nodes, computeOpenEnds(nodes, ed), ed, null);
    expect(spots.map((s) => s.x)).toEqual([-145, 145]);
    expect(spots[1].x - spots[0].x - 236).toBeGreaterThanOrEqual(40);
  });

  it('draws no card where an unconnected step already sits', () => {
    const nodes = [node('t', 0, 0, 'trigger'), node('stray', 0, 150, 'action', { type: 'agent-run' })];
    expect(ghostSpots(nodes, computeOpenEnds(nodes, []), [], null).filter((g) => g.end.nodeId === 't')).toEqual([]);
  });
});

describe('labels', () => {
  it('names branches in plain words', () => {
    const nodes = [node('c', 0, 0, 'action', { type: 'condition' }), node('a', 0, 150, 'action', { type: 'human.approval' })];
    expect(branchPillText(makeFlowEdge('c', 'x', 'true') as Edge, nodes[0])).toBe('Yes');
    expect(branchPillText(makeFlowEdge('c', 'x', 'false') as Edge, nodes[0])).toBe('No');
    expect(branchPillText(makeFlowEdge('a', 'x', 'reject') as Edge, nodes[1])).toBe('Rejected');
    expect(branchPillText(makeFlowEdge('c', 'x', 'next') as Edge, node('p', 0, 0, 'action', { type: 'agent-run' }))).toBeNull();
    expect(branchPillText(makeFlowEdge('r', 'x', 'option', { label: 'Urgent escalation to the support lead' }) as Edge, undefined)).toBe('Urgent escalation to the support lead');
  });

  it('tells End steps after different branches apart', () => {
    const nodes = [node('c', 0, 0, 'action', { type: 'condition' }), node('e1', 0, 150, 'end'), node('e2', 290, 150, 'end')];
    const ed = edges(['c', 'e1', 'true'], ['c', 'e2', 'false']);
    const subs = endSubtitles(nodes, ed);
    expect(subs.get('e1')).not.toEqual(subs.get('e2'));
    expect(subs.get('e1')).toContain('Yes');
  });
});

describe('orphanNote', () => {
  const nodes = [node('t', 0, 0, 'trigger'), node('a', 0, 150, 'action', { type: 'condition' }), node('e', 0, 300, 'end'), node('lone', 290, 0, 'action', { type: 'agent-run' })];
  it('says nothing leads to a step with no line into it', () => {
    expect(orphanNote('lone', nodes, edges(['a', 'e', 'true']))).toBe('Nothing leads to this step');
  });
  it('does not say that for a step that has a line into it from a cut-off part', () => {
    expect(orphanNote('e', nodes, edges(['a', 'e', 'true']))).toBe('Not connected to the trigger');
  });
  it('says nothing for a reachable step', () => {
    expect(orphanNote('e', nodes, edges(['t', 'a', 'next'], ['a', 'e', 'true']))).toBeNull();
  });
});

describe('adding a step where another already sits', () => {
  it('puts the new step one column aside instead of on top of it', () => {
    const nodes = [node('t', 0, 0, 'trigger'), node('c', 0, 150, 'action', { type: 'condition' }), node('stray', -145, 150 + ROW_GAP, 'action', { type: 'agent-run' })];
    const out = addActionStep(nodes, edges(['t', 'c', 'next']), 'c', 'true', 'transform', { type: 'transform' } as never);
    if (!out || out === 'end-in-front') throw new Error('expected a graph');
    const added = out.nodes[out.nodes.length - 1];
    expect(added.position.y).toBe(150 + ROW_GAP);
    expect(Math.abs(added.position.x - -145)).toBeGreaterThanOrEqual(CARD_WIDTH);
  });
});

describe('adding a step on a path that already has one', () => {
  const branchy = () => {
    const nodes = [node('t', 0, 0, 'trigger'), node('c', 0, 150, 'action', { type: 'condition' }), node('yes', -145, 150 + ROW_GAP, 'action', { type: 'agent-run' }), node('yes2', -145, 150 + 2 * ROW_GAP, 'action', { type: 'agent-run' }), node('no', 145, 150 + ROW_GAP, 'end')];
    return { nodes, edges: edges(['t', 'c', 'next'], ['c', 'yes', 'true'], ['yes', 'yes2', 'next'], ['c', 'no', 'false']) };
  };

  it('puts the new step in the branch slot and the old step behind it, one row lower', () => {
    const { nodes, edges: ed } = branchy();
    const out = addActionStep(nodes, ed, 'c', 'true', 'transform', { type: 'transform' } as never);
    if (!out || out === 'end-in-front') throw new Error('expected a graph');
    const added = out.nodes[out.nodes.length - 1];
    const at = (id: string) => out.nodes.find((n) => n.id === id)!.position;
    expect(added.position).toEqual({ x: -145, y: 150 + ROW_GAP }); // exactly where the old step was
    expect(at('yes')).toEqual({ x: -145, y: 150 + 2 * ROW_GAP });
    expect(at('yes2')).toEqual({ x: -145, y: 150 + 3 * ROW_GAP });
    expect(at('no')).toEqual({ x: 145, y: 150 + ROW_GAP });
    expect(out.edges.filter((e) => e.source === 'c' && edgeRoute(e) === 'true').map((e) => e.target)).toEqual([added.id]);
    expect(out.edges.filter((e) => e.source === added.id).map((e) => e.target)).toEqual(['yes']);
    expect(out.edges.filter((e) => e.source === 'yes').map((e) => e.target)).toEqual(['yes2']);
  });

  it('leaves everything where it is when the path is still empty', () => {
    const { nodes, edges: ed } = branchy();
    const out = addActionStep(nodes.filter((n) => n.id !== 'no'), ed.filter((e) => e.target !== 'no'), 'c', 'false', 'transform', { type: 'transform' } as never);
    if (!out || out === 'end-in-front') throw new Error('expected a graph');
    expect(out.nodes.find((n) => n.id === 'yes')!.position).toEqual({ x: -145, y: 150 + ROW_GAP });
  });
});

describe('a new step beside a neighbour', () => {
  const setup = (gap: number) => {
    const nodes = [node('t', 0, 0, 'trigger'), node('c', 0, 150, 'action', { type: 'condition' }), node('other', 145 + CARD_WIDTH + gap, 150 + ROW_GAP, 'action', { type: 'agent-run' })];
    return { nodes, edges: edges(['t', 'c', 'next']) };
  };
  const placed = (gap: number) => {
    const { nodes, edges: ed } = setup(gap);
    const out = addActionStep(nodes, ed, 'c', 'false', 'transform', { type: 'transform' } as never);
    if (!out || out === 'end-in-front') throw new Error('expected a graph');
    return out.nodes[out.nodes.length - 1].position;
  };

  it('moves one column aside when it would leave less than the minimum clear gap', () => {
    expect(MIN_CARD_GAP).toBeGreaterThanOrEqual(24);
    for (const gap of [MIN_CARD_GAP - 14, 4]) {
      const x = placed(gap).x;
      expect(x).toBeGreaterThan(145);
      expect(Math.abs(x - (145 + CARD_WIDTH + gap))).toBeGreaterThanOrEqual(CARD_WIDTH + MIN_CARD_GAP);
    }
  });

  it('stays put when the neighbour leaves the clear gap', () => {
    expect(placed(MIN_CARD_GAP).x).toBe(145);
  });
});
