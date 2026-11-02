import { readFileSync } from 'node:fs';
import path from 'node:path';
import Ajv2020 from 'ajv/dist/2020';
import { describe, expect, it } from 'vitest';
import { deserializeFlow, isBackendNodeConfigured, serializeFlow } from '@/services/flowSerializer';
import { NODE_TYPE_TO_TRIGGER, TRIGGER_CONFIG_KEYS, TRIGGER_TO_NODE_TYPE } from '@/services/flow/serializerTables';
import { GATEWAY_TRIGGER_KINDS } from '@/lib/flow-gateway/triggerKinds';
import type { BackendFlowGraph, BackendNode } from '@/services/flowApi';
import type { Flow, FlowNode, TriggerConfig } from '@/types/flow.types';

const schema = JSON.parse(readFileSync(path.resolve(__dirname, '../../../huf/ai/graph/graph_ir.schema.json'), 'utf8'));
const ajv = new Ajv2020({ strict: false, allErrors: true });
ajv.addSchema(schema);
const validate = ajv.getSchema(`${schema.$id}#/$defs/FlowGraph`)!;
const problems = (g: unknown) => (validate(g), (validate.errors ?? []).map((e) => `${e.instancePath} ${e.message}`));

const trigger = (cfg: TriggerConfig): FlowNode => ({
  id: 't1', type: 'trigger', position: { x: 0, y: 0 },
  data: { label: 'T', nodeType: 'trigger', icon: 'x', configured: true, triggerConfig: cfg },
});
const end: FlowNode = { id: 'e1', type: 'end', position: { x: 0, y: 100 }, data: { label: 'End', nodeType: 'end', icon: 'flag', configured: true, endConfig: { value: 'ok' } } };
const flowOf = (cfg: TriggerConfig): Flow => ({
  id: 'f', name: 'F', status: 'draft', version: 1, createdAt: new Date(0), updatedAt: new Date(0),
  nodes: [trigger(cfg), end],
  edges: [{ id: 'x', source: 't1', target: 'e1' }] as Flow['edges'],
});
const triggerNode = (g: BackendFlowGraph): BackendNode => g.nodes.find((n) => n.id === 't1')!;

describe('chat trigger serialization', () => {
  it.each(GATEWAY_TRIGGER_KINDS)('$id round-trips gateway and params and passes the schema', ({ id, nodeType }) => {
    const cfg = { type: id, gateway: 'Support', params: [{ key: 'keywords', value: ['order', 'refund'] }, { key: 'ignore_bots', value: false }] } as TriggerConfig;
    const graph = serializeFlow(flowOf(cfg));
    expect(triggerNode(graph).type).toBe(nodeType);
    expect(triggerNode(graph).config).toEqual({ gateway: 'Support', params: [{ key: 'keywords', value: ['order', 'refund'] }, { key: 'ignore_bots', value: false }] });
    expect(problems(graph)).toEqual([]);
    const back = deserializeFlow('f', 'F', 'Draft', graph);
    expect(back.nodes.find((n) => n.id === 't1')!.data.triggerConfig).toEqual(cfg);
    expect(serializeFlow(back)).toEqual(graph);
  });

  it('a draft with no channel chosen saves, validates against the schema and reloads still unset', () => {
    for (const { id, nodeType } of GATEWAY_TRIGGER_KINDS) {
      const graph = serializeFlow(flowOf({ type: id } as TriggerConfig));
      expect(triggerNode(graph).type).toBe(nodeType);
      expect(triggerNode(graph).config).toEqual({});
      expect(problems(graph)).toEqual([]);
      expect(isBackendNodeConfigured(triggerNode(graph))).toBe(false);
      const back = deserializeFlow('f', 'F', 'Draft', graph).nodes[0];
      expect(back.data.configured).toBe(false);
      expect(back.data.triggerConfig).toEqual({ type: id });
    }
  });

  it('a blank channel string is kept as typed and still counts as not set up', () => {
    const graph = serializeFlow(flowOf({ type: 'whatsapp', gateway: '', params: [] }));
    expect(triggerNode(graph).config).toEqual({ gateway: '' });
    expect(isBackendNodeConfigured(triggerNode(graph))).toBe(false);
    expect(problems(graph)).toEqual([]);
  });

  it('a chosen channel counts as configured after reload', () => {
    const graph = serializeFlow(flowOf({ type: 'telegram', gateway: 'Sales Bot' }));
    expect(deserializeFlow('f', 'F', 'Draft', graph).nodes[0].data.configured).toBe(true);
  });

  it('keeps only the keys a chat trigger may hold', () => {
    const cfg = { type: 'whatsapp', gateway: 'S', secret: 'leak', cron: '* * * * *' } as unknown as TriggerConfig;
    expect(triggerNode(serializeFlow(flowOf(cfg))).config).toEqual({ gateway: 'S' });
  });
});

describe('trigger type tables', () => {
  it('every editor kind maps to a node type and back, and the three chat kinds come from the shared table', () => {
    for (const [kind, nodeType] of Object.entries(TRIGGER_TO_NODE_TYPE)) {
      expect(NODE_TYPE_TO_TRIGGER[nodeType]).toBe(kind);
      expect(TRIGGER_CONFIG_KEYS[nodeType]).toBeDefined();
    }
    expect(Object.values(TRIGGER_TO_NODE_TYPE).sort()).toEqual(
      ['trigger.doc-event', 'trigger.gateway', 'trigger.schedule', 'trigger.telegram', 'trigger.webhook', 'trigger.whatsapp']
    );
  });

  it('an unknown trigger type never becomes a webhook', () => {
    const graph: BackendFlowGraph = {
      schema_version: '1.0.0', profile: 'flow', fingerprint: 'x', entry: 't1', contract: {} as never,
      nodes: [{ id: 't1', type: 'trigger.smoke-signal', config: { gateway: 'x' }, next: 'e1' } as unknown as BackendNode, { id: 'e1', type: 'output', config: {} } as BackendNode],
    };
    const node = deserializeFlow('f', 'F', 'Draft', graph).nodes[0];
    expect(node.data.triggerConfig).toEqual({ type: undefined });
    expect(triggerNode(serializeFlow(deserializeFlow('f', 'F', 'Draft', graph))).type).toBe('trigger.unset');
  });

  it('webhook, schedule and data triggers are unchanged', () => {
    expect(triggerNode(serializeFlow(flowOf({ type: 'webhook', method: 'POST', secret: 's'.repeat(40) }))).type).toBe('trigger.webhook');
    expect(triggerNode(serializeFlow(flowOf({ type: 'schedule', cron: '0 9 * * *' }))).config).toEqual({ cron: '0 9 * * *' });
    expect(triggerNode(serializeFlow(flowOf({ type: 'doc-event', doctype: 'ToDo', event: 'after_insert' }))).config).toEqual({ doctype: 'ToDo', event: 'after_insert' });
    expect(triggerNode(serializeFlow(flowOf({ type: undefined }))).type).toBe('trigger.unset');
  });
});
