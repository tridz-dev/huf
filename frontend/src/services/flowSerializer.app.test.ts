import { readFileSync } from 'node:fs';
import path from 'node:path';
import Ajv2020 from 'ajv/dist/2020';
import { describe, expect, it } from 'vitest';
import { deserializeFlow, serializeFlow } from '@/services/flowSerializer';
import { triggerLabel } from '@/lib/flow/flowLabels';
import { triggerOptions } from '@/data/triggers';
import type { BackendFlowGraph } from '@/services/flowApi';

const schema = JSON.parse(readFileSync(path.resolve(__dirname, '../../../huf/ai/graph/graph_ir.schema.json'), 'utf8'));
const ajv = new Ajv2020({ strict: false, allErrors: true });
ajv.addSchema(schema);
const validate = ajv.getSchema(`${schema.$id}#/$defs/FlowGraph`)!;

const graph = {
  start: 'start',
  nodes: [
    { id: 'start', type: 'trigger.app', config: { app: 'happiol', entry_policy: 'once_per_member' }, next: 'end', _position: { x: 0, y: 0 } },
    { id: 'end', type: 'output', config: { value: 'ok' }, _position: { x: 0, y: 150 } },
  ],
} as unknown as BackendFlowGraph;

describe('trigger.app in the builder', () => {
  it('loads as an App trigger and saves back unchanged (no rewrite to trigger.unset)', () => {
    const flow = deserializeFlow('f', 'F', 'Active', graph);
    const node = flow.nodes.find((n) => n.id === 'start')!;
    expect(node.data.triggerConfig).toEqual({ type: 'app', app: 'happiol', entry_policy: 'once_per_member' });
    expect(node.data.label).toBe('App trigger');
    expect(node.data.configured).toBe(true);
    expect(triggerLabel('app')).toBe('App trigger');
    const saved = serializeFlow(flow);
    const t = saved.nodes.find((n) => n.id === 'start')!;
    expect(t.type).toBe('trigger.app');
    expect(t.config).toEqual({ app: 'happiol', entry_policy: 'once_per_member' });
    expect(validate(saved), JSON.stringify(validate.errors)).toBe(true);
    expect(serializeFlow(deserializeFlow('f', 'F', 'Active', saved))).toEqual(saved);
  });

  it('is never offered in the trigger palette', () => {
    expect(triggerOptions.map((o) => o.id)).not.toContain('app');
  });
});
