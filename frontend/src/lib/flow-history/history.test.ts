import { describe, it, expect } from 'vitest';
import { HISTORY_LIMIT, emptyHistory, nextRedoLabel, nextUndoLabel, recordChange, redoStep, undoStep, type HistoryState } from './history';
import { describeChange, sameGraph, type GraphSnapshot } from './graphChange';
import { makeFlowEdge } from '../../services/flowSerializer';
import type { FlowEdge, FlowNode } from '../../types/flow.types';

// ── a tiny seeded random generator, so a failing case can be replayed ──
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const node = (id: string, x = 0, y = 0, label = id): FlowNode =>
  ({ id, type: 'action', position: { x, y }, data: { label, nodeType: 'action', configured: true, actionConfig: { type: 'transform', op: 'lower' } } }) as FlowNode;

const start = (): GraphSnapshot => ({ nodes: [{ ...node('t', 0, 0), type: 'trigger', data: { label: 'Trigger', nodeType: 'trigger', configured: true } } as FlowNode], edges: [] });

type Op = (g: GraphSnapshot, r: () => number, n: number) => GraphSnapshot;
const ops: Op[] = [
  // add a step behind the last one
  (g, _r, n) => {
    const last = g.nodes[g.nodes.length - 1];
    const id = `n${n}`;
    return { nodes: [...g.nodes, node(id, last.position.x, last.position.y + 150)], edges: [...g.edges, makeFlowEdge(last.id, id, 'next')] };
  },
  // delete a random non-trigger step
  (g, r) => {
    const pool = g.nodes.filter((x) => x.data.nodeType !== 'trigger');
    if (pool.length === 0) return g;
    const gone = pool[Math.floor(r() * pool.length)].id;
    return { nodes: g.nodes.filter((x) => x.id !== gone), edges: g.edges.filter((e) => e.source !== gone && e.target !== gone) };
  },
  // move a step
  (g, r) => {
    const i = Math.floor(r() * g.nodes.length);
    return { ...g, nodes: g.nodes.map((x, k) => (k === i ? { ...x, position: { x: x.position.x + 10 + Math.floor(r() * 90), y: x.position.y + 7 } } : x)) };
  },
  // edit a step's title
  (g, r, n) => {
    const i = Math.floor(r() * g.nodes.length);
    return { ...g, nodes: g.nodes.map((x, k) => (k === i ? { ...x, data: { ...x.data, label: `title ${n}` } } : x)) };
  },
  // connect two steps
  (g, r, n) => {
    if (g.nodes.length < 3) return g;
    const a = g.nodes[Math.floor(r() * g.nodes.length)];
    const b = g.nodes[Math.floor(r() * g.nodes.length)];
    if (a.id === b.id || g.edges.some((e) => e.source === a.id && e.target === b.id)) return g;
    return { ...g, edges: [...g.edges, makeFlowEdge(a.id, b.id, 'option', { label: `p${n}`, index: n })] };
  },
  // disconnect
  (g, r) => {
    if (g.edges.length === 0) return g;
    const gone = g.edges[Math.floor(r() * g.edges.length)].id;
    return { ...g, edges: g.edges.filter((e) => e.id !== gone) };
  },
];

const key = (g: GraphSnapshot) => JSON.stringify(g);

describe('flow history (property style)', () => {
  it('undoing every recorded change, in order, returns the first graph; redoing them returns the last', () => {
    for (let seed = 1; seed <= 60; seed++) {
      const r = rng(seed);
      let g = start();
      const first = key(g);
      let h: HistoryState = emptyHistory();
      let now = 0;
      let recorded = 0;
      for (let i = 0; i < 40; i++) {
        const next = ops[Math.floor(r() * ops.length)](g, r, i);
        now += 5000; // far apart: no grouping
        const before = h.past.length;
        h = recordChange(h, g, next, now);
        if (h.past.length > before) recorded++;
        g = next;
      }
      expect(h.past.length).toBe(Math.min(recorded, HISTORY_LIMIT));
      const last = key(g);
      let cur = g;
      for (let i = 0; i < recorded; i++) {
        const step = undoStep(h, cur, now);
        expect(step.snapshot).toBeDefined();
        h = step.state;
        cur = step.snapshot as GraphSnapshot;
      }
      expect(key(cur)).toBe(first);
      expect(undoStep(h, cur, now).snapshot).toBeUndefined();
      for (let i = 0; i < recorded; i++) {
        const step = redoStep(h, cur, now);
        h = step.state;
        cur = step.snapshot as GraphSnapshot;
      }
      expect(key(cur)).toBe(last);
      expect(redoStep(h, cur, now).snapshot).toBeUndefined();
    }
  });

  it('undo followed by redo is the identity on the graph and on the stacks', () => {
    for (let seed = 100; seed < 130; seed++) {
      const r = rng(seed);
      let g = start();
      let h = emptyHistory();
      for (let i = 0; i < 12; i++) {
        const next = ops[Math.floor(r() * ops.length)](g, r, i);
        h = recordChange(h, g, next, i * 5000);
        g = next;
      }
      const undone = undoStep(h, g, 1e6);
      if (!undone.snapshot) continue;
      const redone = redoStep(undone.state, undone.snapshot, 1e6);
      expect(key(redone.snapshot as GraphSnapshot)).toBe(key(g));
      expect(redone.state.past.map((e) => e.label)).toEqual(h.past.map((e) => e.label));
      expect(redone.state.future).toEqual([]);
    }
  });

  it('never keeps more than 100 steps, and keeps the newest ones', () => {
    let g = start();
    let h = emptyHistory();
    for (let i = 0; i < 250; i++) {
      const next = ops[0](g, () => 0.5, i);
      h = recordChange(h, g, next, i * 5000);
      g = next;
    }
    expect(h.past.length).toBe(HISTORY_LIMIT);
    let cur = g;
    for (let i = 0; i < 300; i++) {
      const step = undoStep(h, cur, 1e9);
      if (!step.snapshot) break;
      h = step.state;
      cur = step.snapshot;
    }
    // 250 adds, only the newest 100 can be undone
    expect(cur.nodes.length).toBe(g.nodes.length - HISTORY_LIMIT);
    expect(h.future.length).toBe(HISTORY_LIMIT);
  });

  it('a new edit after an undo drops the redo steps', () => {
    let g = start();
    let h = emptyHistory();
    const a = ops[0](g, () => 0.1, 1);
    h = recordChange(h, g, a, 0);
    const undone = undoStep(h, a, 10);
    h = undone.state;
    expect(nextRedoLabel(h)).toBeDefined();
    const b = ops[0](undone.snapshot as GraphSnapshot, () => 0.1, 2);
    h = recordChange(h, undone.snapshot as GraphSnapshot, b, 20);
    expect(h.future).toEqual([]);
    expect(nextUndoLabel(h)).toBeDefined();
    g = b;
    expect(g.nodes.length).toBe(2);
  });
});

describe('grouping', () => {
  const typed = (g: GraphSnapshot, text: string): GraphSnapshot => ({ ...g, nodes: g.nodes.map((n, i) => (i === 1 ? { ...n, data: { ...n.data, label: text } } : n)) });
  const base = (): GraphSnapshot => ({ nodes: [node('t'), node('a')], edges: [] });

  it('keystrokes in one field close together are one undo step that goes back to before the first letter', () => {
    let h = emptyHistory();
    let g = base();
    const original = g;
    const text = 'Send the invoice';
    for (let i = 1; i <= text.length; i++) {
      const next = typed(g, text.slice(0, i));
      h = recordChange(h, g, next, 1000 + i * 120);
      g = next;
    }
    expect(h.past).toHaveLength(1);
    const undone = undoStep(h, g, 9999);
    expect(key(undone.snapshot as GraphSnapshot)).toBe(key(original));
  });

  it('a pause longer than the window starts a new step', () => {
    let h = emptyHistory();
    let g = base();
    for (const [t, at] of [['a', 0], ['ab', 100], ['abc', 5000], ['abcd', 5100]] as const) {
      const next = typed(g, t);
      h = recordChange(h, g, next, at);
      g = next;
    }
    expect(h.past).toHaveLength(2);
  });

  it('edits to two different steps are never merged', () => {
    let h = emptyHistory();
    const g0: GraphSnapshot = { nodes: [node('t'), node('a'), node('b')], edges: [] };
    const g1 = { ...g0, nodes: g0.nodes.map((n) => (n.id === 'a' ? { ...n, data: { ...n.data, label: 'A2' } } : n)) };
    const g2 = { ...g1, nodes: g1.nodes.map((n) => (n.id === 'b' ? { ...n, data: { ...n.data, label: 'B2' } } : n)) };
    h = recordChange(h, g0, g1, 0);
    h = recordChange(h, g1, g2, 100);
    expect(h.past).toHaveLength(2);
  });

  it('an edit right after an undo is its own step even inside the window', () => {
    let h = emptyHistory();
    const g0 = base();
    const g1 = typed(g0, 'x');
    h = recordChange(h, g0, g1, 0);
    const u = undoStep(h, g1, 10);
    const g2 = typed(u.snapshot as GraphSnapshot, 'y');
    h = recordChange(u.state, u.snapshot as GraphSnapshot, g2, 20);
    expect(h.past).toHaveLength(1);
    expect(key(h.past[0].snapshot)).toBe(key(g0));
  });

  it('dragging a step (many small moves) is one step', () => {
    let h = emptyHistory();
    let g = base();
    const start0 = g;
    for (let i = 1; i <= 20; i++) {
      const next = { ...g, nodes: g.nodes.map((n, k) => (k === 1 ? { ...n, position: { x: n.position.x + 5, y: n.position.y + 3 } } : n)) };
      h = recordChange(h, g, next, i * 50);
      g = next;
    }
    expect(h.past).toHaveLength(1);
    expect(h.past[0].label).toBe('Moved a step');
    expect(key(undoStep(h, g, 2000).snapshot as GraphSnapshot)).toBe(key(start0));
  });
});

describe('describeChange', () => {
  it('ignores selection, measured size and live status', () => {
    const g = { nodes: [node('t'), node('a')], edges: [] as FlowEdge[] };
    const view: GraphSnapshot = {
      nodes: g.nodes.map((n) => ({ ...n, selected: true, width: 236, height: 62, dragging: true, data: { ...n.data, status: 'running' as const } })),
      edges: [],
    };
    expect(sameGraph(g, view)).toBe(true);
    expect(describeChange(g, view)).toBeNull();
  });

  it('names the common changes in plain words', () => {
    const g: GraphSnapshot = { nodes: [node('t'), node('a', 0, 150, 'Send email')], edges: [makeFlowEdge('t', 'a', 'next')] };
    expect(describeChange(g, { nodes: g.nodes.slice(0, 1), edges: [] })?.label).toBe('Deleted “Send email”');
    expect(describeChange({ nodes: g.nodes.slice(0, 1), edges: [] }, g)?.label).toBe('Added “Send email”');
    expect(describeChange(g, { ...g, edges: [] })?.label).toBe('Disconnected two steps');
    expect(describeChange({ ...g, edges: [] }, g)?.label).toBe('Connected two steps');
    expect(describeChange(g, { ...g, nodes: [g.nodes[0], { ...g.nodes[1], position: { x: 40, y: 200 } }] })?.label).toBe('Moved a step');
    expect(describeChange(g, { ...g, nodes: [g.nodes[0], { ...g.nodes[1], data: { ...g.nodes[1].data, label: 'Mail' } }] })?.label).toBe('Edited “Mail”');
  });

  it('lets the caller name the change', () => {
    const g: GraphSnapshot = { nodes: [node('t'), node('a')], edges: [] };
    const moved = { ...g, nodes: g.nodes.map((n) => ({ ...n, position: { x: n.position.x + 100, y: 0 } })) };
    expect(describeChange(g, moved, { label: 'Tidied the layout', group: undefined })?.label).toBe('Tidied the layout');
  });
});
