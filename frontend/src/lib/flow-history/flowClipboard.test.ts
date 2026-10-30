// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { cloneSteps, copyLabel, remapIds, uniqueNodeId, type Graph } from './cloneSteps';
import { duplicateSteps } from './flowDuplicate';
import { CLIPBOARD_KEY, buildClipboard, pasteSteps, readClipboard, sanitizeForClipboard, stripSecrets, writeClipboard } from './flowClipboard';
import { edgeRoute, makeFlowEdge } from '../../services/flowSerializer';
import type { FlowNode } from '../../types/flow.types';

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

const step = (id: string, y: number, cfg: Record<string, unknown> = { type: 'transform', op: 'lower', input: {} }, extra: Record<string, unknown> = {}): FlowNode =>
  ({ id, type: 'action', position: { x: 100, y }, data: { label: `Step ${id}`, nodeType: 'action', configured: true, actionConfig: cfg, ...extra } }) as FlowNode;
const trigger = (): FlowNode =>
  ({ id: 'trg', type: 'trigger', position: { x: 100, y: 0 }, data: { label: 'Web request', nodeType: 'trigger', configured: true, triggerConfig: { type: 'webhook', method: 'POST', secret: 'a'.repeat(48) } } }) as FlowNode;

const chain = (n: number): Graph => {
  const nodes = [trigger(), ...Array.from({ length: n }, (_, i) => step(`s${i + 1}`, 150 * (i + 1)))];
  const edges = nodes.slice(1).map((node, i) => makeFlowEdge(nodes[i].id, node.id, 'next'));
  return { nodes, edges };
};

describe('ids and titles', () => {
  it('never hands out an id that is taken, even within one millisecond', () => {
    const taken = new Set<string>();
    const ids = Array.from({ length: 50 }, () => uniqueNodeId(taken, 1700000000000));
    expect(new Set(ids).size).toBe(50);
    for (const id of ids) expect(id).toMatch(/^[a-zA-Z_][a-zA-Z0-9_]*$/);
    expect(Math.max(...ids.map((i) => i.length))).toBeLessThanOrEqual(64);
  });
  it('names copies "X (copy)", then "(copy 2)"', () => {
    expect(copyLabel('Send email', ['Send email'])).toBe('Send email (copy)');
    expect(copyLabel('Send email (copy)', ['Send email', 'Send email (copy)'])).toBe('Send email (copy 2)');
  });
});

describe('remapIds', () => {
  it('only touches whole ids', () => {
    const map = new Map([['node_1', 'node_9']]);
    expect(remapIds({ a: { $from: 'node_1.out.x' }, b: "nodes['node_1'] > 3", c: 'node_10', d: ['node_1'] }, map)).toEqual({
      a: { $from: 'node_9.out.x' },
      b: "nodes['node_9'] > 3",
      c: 'node_10',
      d: ['node_9'],
    });
  });
});

describe('stripSecrets', () => {
  it('empties literal credentials by field name or shape and keeps references', () => {
    const out = stripSecrets({
      url: 'https://x.test',
      headers: { Authorization: 'Bearer abc', 'X-Api-Key': 'k-1', Accept: 'json' },
      input: { password: 'hunter2', token: { $from: 'input.token' }, note: 'Basic dXNlcjpwYXNz' },
    });
    expect(out).toEqual({
      url: 'https://x.test',
      headers: { Authorization: '', 'X-Api-Key': '', Accept: 'json' },
      input: { password: '', token: { $from: 'input.token' }, note: '' },
    });
  });
  it('removes the webhook secret and pinned samples from a copied step', () => {
    const t = sanitizeForClipboard({ ...trigger(), data: { ...trigger().data, sample: { x: 1 } } });
    expect((t.data.triggerConfig as { secret?: string }).secret).toBeUndefined();
    expect(t.data.sample).toBeUndefined();
    expect(JSON.stringify(t)).not.toContain('aaaaaaaa');
  });
});

describe('duplicate', () => {
  it('wires a copy behind a linear step and pushes what followed it down', () => {
    const g = chain(3);
    const r = duplicateSteps(g, ['s2'], 5000)!;
    expect(r.addedIds).toHaveLength(1);
    const copy = r.nodes.find((n) => n.id === r.addedIds[0])!;
    expect(copy.data.label).toBe('Step s2 (copy)');
    expect(copy.position.y).toBe(300 + 150);
    const into = r.edges.filter((e) => e.target === copy.id);
    const out = r.edges.filter((e) => e.source === copy.id);
    expect(into.map((e) => e.source)).toEqual(['s2']);
    expect(out.map((e) => e.target)).toEqual(['s3']);
    expect(r.edges.some((e) => e.source === 's2' && e.target === 's3')).toBe(false);
    expect(r.nodes.find((n) => n.id === 's3')!.position.y).toBe(450 + 150);
    // original untouched
    expect(r.nodes.find((n) => n.id === 's2')).toEqual(g.nodes.find((n) => n.id === 's2'));
  });
  it('appends after the last step', () => {
    const r = duplicateSteps(chain(1), ['s1'], 9)!;
    expect(r.edges).toHaveLength(2);
  });
  it('puts a branching step beside the original, unconnected', () => {
    const g: Graph = { nodes: [trigger(), step('c', 150, { type: 'condition', expression: 'x' }), step('y', 300), step('n', 300)], edges: [makeFlowEdge('trg', 'c', 'next'), makeFlowEdge('c', 'y', 'true'), makeFlowEdge('c', 'n', 'false')] };
    const r = duplicateSteps(g, ['c'], 7)!;
    expect(r.wiredAfter).toBeUndefined();
    expect(r.edges).toHaveLength(g.edges.length);
    const copy = r.nodes.find((n) => n.id === r.addedIds[0])!;
    expect(copy.position).toEqual({ x: 148, y: 222 });
  });
  it('leaves the trigger alone: a flow has one', () => {
    const r = duplicateSteps(chain(1), ['trg'], 1)!;
    expect(r.skippedTrigger).toBe(true);
    expect(r.addedIds).toEqual([]);
  });
  it('drops the pinned sample from the copy but keeps the settings, and does not share objects with the original', () => {
    const g = chain(1);
    g.nodes[1] = step('s1', 150, { type: 'tool-call', tool_id: 'x', input: { to: 'a@b.c' } }, { sample: { out: 1 } });
    const r = duplicateSteps(g, ['s1'], 3)!;
    const copy = r.nodes.find((n) => n.id === r.addedIds[0])!;
    expect(copy.data.sample).toBeUndefined();
    expect((copy.data.actionConfig as unknown as { input: { to: string } }).input.to).toBe('a@b.c');
    (copy.data.actionConfig as unknown as { input: { to: string } }).input.to = 'changed';
    expect((g.nodes[1].data.actionConfig as unknown as { input: { to: string } }).input.to).toBe('a@b.c');
  });
  it('several steps are copied together with the connections between them', () => {
    const r = duplicateSteps(chain(3), ['s1', 's2'], 11)!;
    expect(r.addedIds).toHaveLength(2);
    const [a, b] = r.addedIds;
    expect(r.edges.some((e) => e.source === a && e.target === b)).toBe(true);
    expect(r.edges.some((e) => e.source === 's1' && e.target === a)).toBe(false);
  });
});

describe('copy and paste (property style)', () => {
  beforeEach(() => {
    const data = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => data.get(k) ?? null,
      setItem: (k: string, v: string) => void data.set(k, v),
      removeItem: (k: string) => void data.delete(k),
      clear: () => data.clear(),
    });
  });

  const randomGraph = (seed: number): Graph => {
    const r = rng(seed);
    const count = 3 + Math.floor(r() * 6);
    const nodes: FlowNode[] = [trigger()];
    for (let i = 1; i <= count; i++) {
      nodes.push(step(`n${i}`, 150 * i, { type: 'tool-call', tool_id: 'http_request', input: { url: `u${i}`, headers: { Authorization: `Bearer tok${i}` }, ref: { $from: `n${Math.max(1, i - 1)}.out` }, expr: `nodes['n${Math.max(1, i - 1)}']` } }, { sample: { secret: `pin${i}` } }));
    }
    const edges = nodes.slice(1).map((n, i) => makeFlowEdge(nodes[i].id, n.id, 'next'));
    // some extra forward edges
    for (let k = 0; k < 2; k++) {
      const a = 1 + Math.floor(r() * (count - 1));
      const b = a + 1 + Math.floor(r() * (count - a));
      if (b <= count) edges.push(makeFlowEdge(`n${a}`, `n${b}`, 'option', { label: `p${k}`, index: k + 5 }));
    }
    return { nodes, edges };
  };

  it('pasted steps get fresh ids, keep the links between them, point their references at the copies, and carry no secrets', () => {
    for (let seed = 1; seed <= 40; seed++) {
      const g = randomGraph(seed);
      const r = rng(seed * 7);
      const ids = g.nodes.filter((n) => n.id !== 'trg' && r() < 0.6).map((n) => n.id);
      if (ids.length === 0) continue;
      const payload = buildClipboard(g, ids, 'flowA', 1)!;
      const text = JSON.stringify(payload);
      expect(text).not.toMatch(/Bearer tok|pin\d|"secret":"a/);
      const other: Graph = { nodes: [trigger(), step('x1', 150)], edges: [makeFlowEdge('trg', 'x1', 'next')] };
      for (const [flowId, target] of [['flowA', g], ['flowB', other]] as const) {
        const out = pasteSteps(payload, target, flowId, 1700000000000, 0);
        expect(out.addedIds).toHaveLength(ids.length);
        const all = out.nodes.map((n) => n.id);
        expect(new Set(all).size).toBe(all.length);
        const added = out.nodes.filter((n) => out.addedIds.includes(n.id));
        // old ids of the copied steps are not inside the pasted copies' own references
        const copiedOld = ids;
        for (const n of added) {
          const body = JSON.stringify(n.data.actionConfig);
          for (const oldId of copiedOld) expect(body).not.toMatch(new RegExp(`(?<![A-Za-z0-9_])${oldId}(?![A-Za-z0-9_])`));
        }
        // links among copied steps preserved one-to-one, same route
        const expectedLinks = g.edges.filter((e) => ids.includes(e.source) && ids.includes(e.target));
        const newEdges = out.edges.filter((e) => out.addedIds.includes(e.source) && out.addedIds.includes(e.target));
        expect(newEdges).toHaveLength(expectedLinks.length);
        for (const e of expectedLinks) {
          const from = out.addedIds[ids.indexOf(e.source)];
          const to = out.addedIds[ids.indexOf(e.target)];
          const hit = newEdges.find((x) => x.source === from && x.target === to && edgeRoute(x) === edgeRoute(e));
          expect(hit).toBeDefined();
        }
        // no edge leaves a pasted step for an old step, nobody links into the pasted steps from outside
        expect(out.edges.filter((e) => out.addedIds.includes(e.target) && !out.addedIds.includes(e.source))).toHaveLength(0);
        // the target's own steps are untouched
        for (const n of target.nodes) expect(out.nodes.find((x) => x.id === n.id)!.data).toEqual(n.data);
        // pasted steps are selected, nothing else is
        expect(out.nodes.filter((n) => n.selected).map((n) => n.id).sort()).toEqual([...out.addedIds].sort());
      }
    }
  });

  it('lands beside the originals in the same flow, and to the right of the others in a different flow; a second paste moves along', () => {
    const g = chain(2);
    const payload = buildClipboard(g, ['s1'], 'A', 1)!;
    const same = pasteSteps(payload, g, 'A', 5, 0);
    const copy = same.nodes.find((n) => n.id === same.addedIds[0])!;
    expect(copy.position).toEqual({ x: 148, y: 222 });
    const again = pasteSteps(payload, g, 'A', 6, 1);
    expect(again.nodes.find((n) => n.id === again.addedIds[0])!.position).toEqual({ x: 196, y: 294 });
    const elsewhere = pasteSteps(payload, { nodes: [trigger()], edges: [] }, 'B', 7, 0);
    const moved = elsewhere.nodes.find((n) => n.id === elsewhere.addedIds[0])!;
    expect(moved.position.x).toBe(100 + 236 + 80);
    expect(moved.data.label).toBe('Step s1');
  });

  it('a pasted webhook trigger gets a new secret, and is skipped when the flow already has a trigger', () => {
    const g = chain(1);
    const payload = buildClipboard(g, ['trg', 's1'], 'A', 1)!;
    const into = pasteSteps(payload, { nodes: [], edges: [] }, 'B', 9, 0);
    const trg = into.nodes.find((n) => n.data.nodeType === 'trigger')!;
    const secret = (trg.data.triggerConfig as { secret?: string }).secret!;
    expect(secret).toMatch(/^[0-9a-f]{48}$/);
    expect(secret).not.toBe('a'.repeat(48));
    const skipped = pasteSteps(payload, g, 'B', 10, 0);
    expect(skipped.skippedTrigger).toBe(true);
    expect(skipped.addedIds).toHaveLength(1);
  });

  it('round-trips through localStorage and ignores junk', () => {
    const g = chain(2);
    const payload = buildClipboard(g, ['s1', 's2'], 'A', 1)!;
    expect(writeClipboard(payload)).toBe(true);
    expect(readClipboard()?.nodes.map((n) => n.id)).toEqual(['s1', 's2']);
    localStorage.setItem(CLIPBOARD_KEY, '{"v":2}');
    expect(readClipboard()).toBeNull();
    localStorage.setItem(CLIPBOARD_KEY, 'not json');
    expect(readClipboard()).toBeNull();
  });

  it('cloneSteps keeps a router fallback only when its target was copied too', () => {
    const g: Graph = { nodes: [trigger(), step('r', 150, { type: 'router', default: 'a' }), step('a', 300), step('b', 300)], edges: [] };
    const both = cloneSteps(g, ['r', 'a'], g.nodes.map((n) => n.id), { now: 1, place: (n) => n.position });
    expect((both.nodes[0].data.actionConfig as { default?: string }).default).toBe(both.idMap.get('a'));
    const alone = cloneSteps(g, ['r'], g.nodes.map((n) => n.id), { now: 2, place: (n) => n.position });
    expect((alone.nodes[0].data.actionConfig as { default?: string }).default).toBeUndefined();
  });
});
