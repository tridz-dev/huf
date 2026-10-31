import { describe, expect, it } from 'vitest';
import { deserializeFlow, serializeFlow } from './flowSerializer';

const step = (id: string, x: number, y: number, label = id) => ({
  id, type: 'end', _position: { x, y }, label, config: {}, next: null,
}) as never;

// Group 1 (t -> a, b) has two cards 4px apart; group 2 (p -> q) is roomy but at odd spots.
const graph = {
  nodes: [
    { id: 't', type: 'trigger.webhook', _position: { x: 250, y: 250 }, label: 'T', config: { method: 'POST' }, next: ['a', 'b'] },
    step('a', 130, 400), step('b', 370, 400),
    { id: 'p', type: 'trigger.webhook', _position: { x: 1203, y: 257 }, label: 'P', config: { method: 'POST' }, next: 'q' },
    step('q', 1203, 407),
  ],
} as never;

describe('a rename must not rewrite positions of cards that were fine', () => {
  it('keeps the roomy group exactly where it was saved after load, rename and save', () => {
    const flow = deserializeFlow('f', 'F', 'Draft', graph);
    const xs = (id: string) => flow.nodes.find((n) => n.id === id)!.position.x;
    expect(Math.abs(xs('b') - xs('a'))).toBeGreaterThanOrEqual(236 + 24); // the squeezed group was laid out again
    const renamed = { ...flow, nodes: flow.nodes.map((n) => (n.id === 'q' ? { ...n, data: { ...n.data, label: 'Renamed' } } : n)) };
    const saved = serializeFlow(renamed as never).nodes;
    expect(saved.find((n) => n.id === 'p')?._position).toEqual({ x: 1203, y: 257 });
    expect(saved.find((n) => n.id === 'q')?._position).toEqual({ x: 1203, y: 407 });
  });
});
