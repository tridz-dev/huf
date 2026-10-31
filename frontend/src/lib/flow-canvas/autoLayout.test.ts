// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { autoLayout, CARD_WIDTH, COLUMN_GAP, ORIGIN_X, ORIGIN_Y, ROW_GAP } from './autoLayout';
import { tidyPositions } from '../flow/flowLayout';
import { routeEdge, routeLoopBack, segmentHitsRect, type Rect } from '../flow-graph/edgeRouting';
import { deserializeFlow } from '../../services/flowSerializer';
import { FLOW_TEMPLATES } from '../../data/flowTemplates';
import { loopBacks, computeOpenEnds } from '../flow-graph/flowCanvasGraph';
import { edgeRoute } from '../../services/flowSerializer';
import { branchHandlesFor } from '../flow/flowBranches';

const CARD_HEIGHT = 100;
const n = (id: string) => ({ id, position: { x: 0, y: 0 } });
const e = (source: string, target: string, order?: number) => ({ source, target, order });

function rects(p: Record<string, { x: number; y: number }>): Map<string, Rect> {
  return new Map(Object.entries(p).map(([id, v]) => [id, { x: v.x, y: v.y, width: CARD_WIDTH, height: CARD_HEIGHT }]));
}

/** Every pair of cards keeps clear space between them. */
function expectNoOverlap(p: Record<string, { x: number; y: number }>) {
  const r = [...rects(p).entries()];
  for (let i = 0; i < r.length; i++) {
    for (let j = i + 1; j < r.length; j++) {
      const [ia, a] = r[i];
      const [ib, b] = r[j];
      const apart = a.x + a.width + 20 <= b.x || b.x + b.width + 20 <= a.x || a.y + a.height + 20 <= b.y || b.y + b.height + 20 <= a.y;
      expect(apart, `${ia} overlaps ${ib}`).toBe(true);
    }
  }
}

/** The drawn line of a connection never passes behind another card (its own two ends excepted). */
function expectLinesClear(p: Record<string, { x: number; y: number }>, edges: Array<{ source: string; target: string }>) {
  const all = rects(p);
  for (const ed of edges) {
    const s = all.get(ed.source) as Rect;
    const t = all.get(ed.target) as Rect;
    const routed = routeEdge({ x: s.x + s.width / 2, y: s.y + s.height }, { x: t.x + t.width / 2, y: t.y }, [...all.values()]);
    for (let i = 0; i < routed.points.length - 1; i++) {
      if (i === 0 || i === routed.points.length - 2) continue; // leaving / entering the card's own border
      for (const [id, r] of all) expect(segmentHitsRect(routed.points[i], routed.points[i + 1], r, 4), `${ed.source}>${ed.target} runs behind ${id}`).toBe(false);
    }
  }
}

describe('autoLayout', () => {
  it('keeps a straight run on one vertical line with even rows', () => {
    const p = autoLayout([n('a'), n('b'), n('c'), n('d')], [e('a', 'b'), e('b', 'c'), e('c', 'd')]);
    expect(Object.values(p).map((v) => v.x)).toEqual([ORIGIN_X, ORIGIN_X, ORIGIN_X, ORIGIN_X]);
    expect(Object.values(p).map((v) => v.y)).toEqual([0, 1, 2, 3].map((i) => ORIGIN_Y + i * ROW_GAP));
  });

  it('fans branches out in their own order, centred under their step, and joins below', () => {
    const p = autoLayout([n('t'), n('c'), n('yes'), n('no'), n('end')], [e('t', 'c'), e('c', 'yes', 0), e('c', 'no', 1), e('yes', 'end'), e('no', 'end')]);
    expect(p.yes.x).toBeLessThan(p.no.x);
    expect(p.no.x - p.yes.x).toBe(COLUMN_GAP);
    expect(p.c.x).toBe((p.yes.x + p.no.x) / 2);
    expect(p.end.x).toBe(p.c.x);
    expect(p.yes.y).toBe(p.no.y);
    expect(p.end.y).toBe(ORIGIN_Y + 3 * ROW_GAP);
  });

  it('puts the branch listed second on the right even when its step is listed first', () => {
    const p = autoLayout([n('t'), n('c'), n('no'), n('yes')], [e('t', 'c'), e('c', 'no', 1), e('c', 'yes', 0)]);
    expect(p.yes.x).toBeLessThan(p.no.x);
  });

  it('gives a connection that skips rows a lane of its own instead of running behind a step', () => {
    const nodes = ['t', 'c', 'a', 'b', 'end'].map(n);
    const edges = [e('t', 'c'), e('c', 'a', 0), e('c', 'end', 1), e('a', 'b'), e('b', 'end')];
    const p = autoLayout(nodes, edges);
    expectNoOverlap(p);
    expectLinesClear(p, edges);
  });

  it('survives a cycle, a lone step and unknown ids', () => {
    const p = autoLayout([n('a'), n('b'), n('lone')], [e('a', 'b'), e('b', 'a'), e('a', 'ghost')]);
    expect(Object.keys(p).sort()).toEqual(['a', 'b', 'lone']);
    for (const v of Object.values(p)) expect(Number.isFinite(v.x) && Number.isFinite(v.y)).toBe(true);
    expectNoOverlap(p);
  });

  it('is deterministic', () => {
    const nodes = ['t', 'c', 'a', 'b', 'end'].map(n);
    const edges = [e('t', 'c'), e('c', 'a', 0), e('c', 'b', 1), e('a', 'end'), e('b', 'end')];
    expect(autoLayout(nodes, edges)).toEqual(autoLayout(nodes, edges));
  });

  it('lays out 60 steps with a branch every fifth step without overlap, quickly', () => {
    const nodes = Array.from({ length: 60 }, (_, i) => n(`s${i}`));
    const edges: Array<{ source: string; target: string; order?: number }> = [];
    for (let i = 0; i < 59; i++) edges.push(e(`s${i}`, `s${i + 1}`, 0));
    for (let i = 0; i + 7 < 60; i += 5) edges.push(e(`s${i}`, `s${i + 7}`, 1));
    const started = Date.now();
    const p = autoLayout(nodes, edges);
    expect(Date.now() - started).toBeLessThan(1500);
    expectNoOverlap(p);
  });
});

/** Steps and connections of a template as the editor loads them, with every saved position taken away. */
function templateGraph(id: string) {
  const tpl = FLOW_TEMPLATES.find((t) => t.id === id);
  if (!tpl) throw new Error(`no template ${id}`);
  const graph = JSON.parse(JSON.stringify(tpl.graph));
  for (const node of graph.nodes) delete node._position;
  return deserializeFlow(id, id, 'draft', graph);
}

describe('tidyPositions on the ready-made templates', () => {
  for (const tpl of FLOW_TEMPLATES) {
    it(`${tpl.id}: no overlap, no line behind a step, branches in order`, () => {
      const flow = templateGraph(tpl.id);
      const p = tidyPositions(flow.nodes, flow.edges);
      expectNoOverlap(p);
      expectLinesClear(p, flow.edges);
      for (const node of flow.nodes) {
        const cfg = node.data.actionConfig as ({ type?: string } & Record<string, unknown>) | undefined;
        const handles = branchHandlesFor(cfg?.type, cfg);
        const xs = handles.map((h) => flow.edges.find((ed) => ed.source === node.id && edgeRoute(ed) === h.route)).map((ed) => (ed ? p[ed.target]?.x : undefined));
        const known = xs.filter((v): v is number => v !== undefined);
        // Branches that sit on the same row as each other keep their order.
        if (known.length === 2 && handles.length === 2 && p[flow.edges.find((ed) => ed.source === node.id && edgeRoute(ed) === handles[0].route)!.target].y === p[flow.edges.find((ed) => ed.source === node.id && edgeRoute(ed) === handles[1].route)!.target].y) {
          expect(known[0]).toBeLessThan(known[1]);
        }
      }
    });
  }

  it('the loop template draws its return line clear of every step', () => {
    const flow = templateGraph('each-item');
    const p = tidyPositions(flow.nodes, flow.edges);
    const all = rects(p);
    const backs = loopBacks(flow.nodes, flow.edges, computeOpenEnds(flow.nodes, flow.edges));
    expect(backs.length).toBeGreaterThan(0);
    for (const { leafId, loopId } of backs) {
      const leaf = all.get(leafId) as Rect;
      const routed = routeLoopBack({ x: leaf.x + leaf.width / 2, y: leaf.y + leaf.height }, all.get(loopId) as Rect, [...all.values()]);
      for (let i = 1; i < routed.points.length - 2; i++) {
        for (const [id, r] of all) expect(segmentHitsRect(routed.points[i], routed.points[i + 1], r, 4), `return line runs behind ${id}`).toBe(false);
      }
    }
  });
});
