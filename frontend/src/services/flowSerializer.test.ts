import { describe, it, expect } from 'vitest';
import {
  serializeFlow,
  deserializeFlow,
  mapBackendStatusToFrontend,
} from '@/services/flowSerializer';
import type { Flow, FlowNode, FlowEdge } from '@/types/flow.types';
import type { BackendFlowGraph } from '@/services/flowApi';

describe('flowSerializer', () => {
  describe('mapFrontendNodeTypeToBackend', () => {
    it('maps agent-run action type to agent.run', () => {
      const flow = createTestFlow([
        createActionNode('node1', 'agent-run'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('agent.run');
    });

    it('maps tool-call action type to tool.call', () => {
      const flow = createTestFlow([
        createActionNode('node1', 'tool-call'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('tool.call');
    });

    it('maps router action type to router.llm', () => {
      const flow = createTestFlow([
        createActionNode('node1', 'router'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('router.llm');
    });

    it('maps human.approval action type to human.approval', () => {
      const flow = createTestFlow([
        createActionNode('node1', 'human.approval'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('human.approval');
    });

    it('maps condition action type to condition', () => {
      const flow = createTestFlow([
        createActionNode('node1', 'condition'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('condition');
    });

    it('maps http-request action type to http_request', () => {
      const flow = createTestFlow([
        createActionNode('node1', 'http-request'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('http_request');
    });

    it('maps transform action type to transform', () => {
      const flow = createTestFlow([
        createActionNode('node1', 'transform'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('transform');
    });

    it('maps loop action type to loop', () => {
      const flow = createTestFlow([
        createActionNode('node1', 'loop'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('loop');
    });

    it('maps end node type to end', () => {
      const flow = createTestFlow([
        {
          id: 'node1',
          type: 'end',
          position: { x: 0, y: 0 },
          data: {
            nodeType: 'end',
            label: 'End',
            icon: 'CheckCircle2',
            configured: true,
          },
        },
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('end');
    });

    it('maps trigger with schedule type to trigger.schedule', () => {
      const flow = createTestFlow([
        {
          id: 'trigger1',
          type: 'trigger',
          position: { x: 0, y: 0 },
          data: {
            nodeType: 'trigger',
            label: 'Schedule',
            icon: 'Clock',
            configured: true,
            triggerConfig: {
              type: 'schedule',
              intervalType: 'hours',
              interval: 1,
            },
          },
        },
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('trigger.schedule');
    });

    it('maps trigger with doc-event type to trigger.doc-event', () => {
      const flow = createTestFlow([
        {
          id: 'trigger1',
          type: 'trigger',
          position: { x: 0, y: 0 },
          data: {
            nodeType: 'trigger',
            label: 'Doc Event',
            icon: 'Database',
            configured: true,
            triggerConfig: {
              type: 'doc-event',
              doctype: 'Task',
              event: 'save',
            },
          },
        },
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('trigger.doc-event');
    });

    it('maps trigger with webhook type (or default) to trigger.webhook', () => {
      const flow = createTestFlow([
        {
          id: 'trigger1',
          type: 'trigger',
          position: { x: 0, y: 0 },
          data: {
            nodeType: 'trigger',
            label: 'Webhook',
            icon: 'Webhook',
            configured: true,
            triggerConfig: {
              type: 'webhook',
              url: 'https://example.com/webhook',
              method: 'POST',
            },
          },
        },
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('trigger.webhook');
    });
  });

  describe('KNOWN DEFECT: unmapped action types (8 fallback cases)', () => {
    // These 8 action types are not explicitly mapped in mapFrontendNodeTypeToBackend
    // and fall through to the default: return 'tool.call' at line ~80.
    // This causes data loss because tool.call nodes without a tool_name are rejected
    // by the engine at flow_engine.py:571-573.
    // These tests document the current broken behavior.

    it("KNOWN DEFECT: 'code' action silently serializes to tool.call", () => {
      const flow = createTestFlow([
        createActionNodeWithUnmappedType('node1', 'code'),
      ]);
      const serialized = serializeFlow(flow);
      // This node will serialize to 'tool.call' even though it's not one
      expect(serialized.nodes[0].type).toBe('tool.call');
    });

    it("KNOWN DEFECT: 'email' action silently serializes to tool.call", () => {
      // tool.call with no tool_name is rejected by engine at flow_engine.py:571-573
      const flow = createTestFlow([
        createActionNodeWithUnmappedType('node1', 'email'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('tool.call');
    });

    it("KNOWN DEFECT: 'webhook' action silently serializes to tool.call", () => {
      // Note: 'webhook' here refers to an action webhook, not the trigger webhook.
      // tool.call with no tool_name is rejected by engine at flow_engine.py:571-573
      const flow = createTestFlow([
        createActionNodeWithUnmappedType('node1', 'webhook'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('tool.call');
    });

    it("KNOWN DEFECT: 'file' action silently serializes to tool.call", () => {
      // tool.call with no tool_name is rejected by engine at flow_engine.py:571-573
      const flow = createTestFlow([
        createActionNodeWithUnmappedType('node1', 'file'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('tool.call');
    });

    it("KNOWN DEFECT: 'date' action silently serializes to tool.call", () => {
      // tool.call with no tool_name is rejected by engine at flow_engine.py:571-573
      const flow = createTestFlow([
        createActionNodeWithUnmappedType('node1', 'date'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('tool.call');
    });

    it("KNOWN DEFECT: 'slack' action silently serializes to tool.call", () => {
      // tool.call with no tool_name is rejected by engine at flow_engine.py:571-573
      const flow = createTestFlow([
        createActionNodeWithUnmappedType('node1', 'slack'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('tool.call');
    });

    it("KNOWN DEFECT: 'sheets' action silently serializes to tool.call", () => {
      // tool.call with no tool_name is rejected by engine at flow_engine.py:571-573
      const flow = createTestFlow([
        createActionNodeWithUnmappedType('node1', 'sheets'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('tool.call');
    });

    it("KNOWN DEFECT: 'notion' action silently serializes to tool.call", () => {
      // tool.call with no tool_name is rejected by engine at flow_engine.py:571-573
      const flow = createTestFlow([
        createActionNodeWithUnmappedType('node1', 'notion'),
      ]);
      const serialized = serializeFlow(flow);
      expect(serialized.nodes[0].type).toBe('tool.call');
    });
  });

  describe('Round-trip identity (serializeFlow -> deserializeFlow)', () => {
    it('preserves mapped action types through round trip', () => {
      const flow = createTestFlow([
        createActionNode('agent1', 'agent-run'),
        createActionNode('router1', 'router'),
        createActionNode('condition1', 'condition'),
      ]);

      const serialized = serializeFlow(flow);
      const deserialized = deserializeFlow('flow1', 'Test Flow', 'Draft', serialized);

      // Check that the nodes come back with correct types
      expect(deserialized.nodes[0].type).toBe('action');
      expect(deserialized.nodes[0].data?.actionConfig?.type).toBe('agent-run');

      expect(deserialized.nodes[1].type).toBe('action');
      expect(deserialized.nodes[1].data?.actionConfig?.type).toBe('router');

      expect(deserialized.nodes[2].type).toBe('action');
      expect(deserialized.nodes[2].data?.actionConfig?.type).toBe('condition');
    });

    it('LOSES IDENTITY for unmapped action types: they come back as tool-call', () => {
      const flow = createTestFlow([
        createActionNodeWithUnmappedType('email1', 'email'),
      ]);

      const serialized = serializeFlow(flow);
      const deserialized = deserializeFlow('flow1', 'Test Flow', 'Draft', serialized);

      // The 'email' action type is NOT preserved; it comes back as 'tool-call'
      expect(serialized.nodes[0].type).toBe('tool.call');
      expect(deserialized.nodes[0].data?.actionConfig?.type).toBe('tool-call');
    });

    it('LOSES IDENTITY for human-input trigger: comes back as webhook', () => {
      const flow = createTestFlow([
        {
          id: 'trigger1',
          type: 'trigger',
          position: { x: 0, y: 0 },
          data: {
            nodeType: 'trigger',
            label: 'Human Input',
            icon: 'UserInput',
            configured: true,
            triggerConfig: {
              type: 'human-input',
            } as any,
          },
        },
      ]);

      const serialized = serializeFlow(flow);
      // Unmapped trigger type should default to trigger.webhook
      expect(serialized.nodes[0].type).toBe('trigger.webhook');

      const deserialized = deserializeFlow('flow1', 'Test Flow', 'Draft', serialized);
      // It comes back as webhook trigger, not human-input
      expect(deserialized.nodes[0].data?.triggerConfig?.type).toBe('webhook');
    });

    it('preserves trigger types through round trip', () => {
      const flow = createTestFlow([
        {
          id: 'trigger1',
          type: 'trigger',
          position: { x: 0, y: 0 },
          data: {
            nodeType: 'trigger',
            label: 'Schedule',
            icon: 'Clock',
            configured: true,
            triggerConfig: {
              type: 'schedule',
              intervalType: 'days',
              interval: 1,
            },
          },
        },
      ]);

      const serialized = serializeFlow(flow);
      const deserialized = deserializeFlow('flow1', 'Test Flow', 'Draft', serialized);

      expect(deserialized.nodes[0].type).toBe('trigger');
      expect(deserialized.nodes[0].data?.triggerConfig?.type).toBe('schedule');
    });

    it('preserves end node through round trip', () => {
      const flow = createTestFlow([
        {
          id: 'end1',
          type: 'end',
          position: { x: 500, y: 500 },
          data: {
            nodeType: 'end',
            label: 'End Flow',
            icon: 'CheckCircle2',
            configured: true,
          },
        },
      ]);

      const serialized = serializeFlow(flow);
      const deserialized = deserializeFlow('flow1', 'Test Flow', 'Draft', serialized);

      expect(deserialized.nodes[0].type).toBe('end');
    });
  });

  describe('omitType - stripping the type discriminator', () => {
    it('removes the type field from config', () => {
      const flow = createTestFlow([
        createActionNode('agent1', 'agent-run'),
      ]);
      const serialized = serializeFlow(flow);

      // The config should not have a 'type' field
      expect(serialized.nodes[0].config).not.toHaveProperty('type');
    });

    it('preserves other config fields while removing type', () => {
      const node: FlowNode = {
        id: 'agent1',
        type: 'action',
        position: { x: 0, y: 0 },
        data: {
          nodeType: 'action',
          label: 'Run Agent',
          icon: 'Bot',
          configured: true,
          actionConfig: {
            type: 'agent-run',
            agent_name: 'my-agent',
            prompt_template: 'template',
            save_response_to_context: 'response',
            inject_flow_context: true,
          },
        },
      };

      const flow = createTestFlow([node]);
      const serialized = serializeFlow(flow);

      expect(serialized.nodes[0].config).not.toHaveProperty('type');
      expect(serialized.nodes[0].config).toHaveProperty('agent_name', 'my-agent');
      expect(serialized.nodes[0].config).toHaveProperty('prompt_template', 'template');
      expect(serialized.nodes[0].config).toHaveProperty('save_response_to_context', 'response');
      expect(serialized.nodes[0].config).toHaveProperty('inject_flow_context', true);
    });

    it('handles trigger config type removal', () => {
      const node: FlowNode = {
        id: 'trigger1',
        type: 'trigger',
        position: { x: 0, y: 0 },
        data: {
          nodeType: 'trigger',
          label: 'Schedule',
          icon: 'Clock',
          configured: true,
          triggerConfig: {
            type: 'schedule',
            intervalType: 'hours',
            interval: 2,
            timezone: 'UTC',
          },
        },
      };

      const flow = createTestFlow([node]);
      const serialized = serializeFlow(flow);

      expect(serialized.nodes[0].config).not.toHaveProperty('type');
      expect(serialized.nodes[0].config).toHaveProperty('intervalType', 'hours');
      expect(serialized.nodes[0].config).toHaveProperty('interval', 2);
      expect(serialized.nodes[0].config).toHaveProperty('timezone', 'UTC');
    });
  });

  describe('Position/label/icon sidecar fields', () => {
    it('preserves _position, _label, _icon through serialization', () => {
      const node: FlowNode = {
        id: 'node1',
        type: 'action',
        position: { x: 150, y: 300 },
        data: {
          nodeType: 'action',
          label: 'Custom Label',
          icon: 'CustomIcon',
          configured: true,
          actionConfig: { type: 'tool-call' },
        },
      };

      const flow = createTestFlow([node]);
      const serialized = serializeFlow(flow);

      expect(serialized.nodes[0]._position).toEqual({ x: 150, y: 300 });
      expect(serialized.nodes[0]._label).toBe('Custom Label');
      expect(serialized.nodes[0]._icon).toBe('CustomIcon');
    });

    it('preserves _position through round trip', () => {
      const node: FlowNode = {
        id: 'node1',
        type: 'action',
        position: { x: 200, y: 400 },
        data: {
          nodeType: 'action',
          label: 'Test',
          icon: 'Play',
          configured: true,
          actionConfig: { type: 'tool-call' },
        },
      };

      const flow = createTestFlow([node]);
      const serialized = serializeFlow(flow);
      const deserialized = deserializeFlow('flow1', 'Test', 'Draft', serialized);

      expect(deserialized.nodes[0].position).toEqual({ x: 200, y: 400 });
    });

    it('auto-layouts nodes vertically when _position is absent', () => {
      const backend: BackendFlowGraph = {
        schema_version: 1,
        id: 'flow1',
        version: 1,
        entry: 'node1',
        nodes: [
          {
            id: 'node1',
            type: 'tool.call',
            config: {},
            // _position is absent
            _label: 'Node 1',
          },
          {
            id: 'node2',
            type: 'tool.call',
            config: {},
            // _position is absent
            _label: 'Node 2',
          },
          {
            id: 'node3',
            type: 'tool.call',
            config: {},
            // _position is absent
            _label: 'Node 3',
          },
        ],
        edges: [],
        settings: { mode: 'normal', max_hops: 100 },
        metadata: { name: 'Test', description: '', category: '' },
      };

      const deserialized = deserializeFlow('flow1', 'Test', 'Draft', backend);

      // Should auto-layout: (x: 250, y: index * 150)
      expect(deserialized.nodes[0].position).toEqual({ x: 250, y: 0 });
      expect(deserialized.nodes[1].position).toEqual({ x: 250, y: 150 });
      expect(deserialized.nodes[2].position).toEqual({ x: 250, y: 300 });
    });

    it('preserves _label and _icon through round trip', () => {
      const node: FlowNode = {
        id: 'node1',
        type: 'action',
        position: { x: 100, y: 200 },
        data: {
          nodeType: 'action',
          label: 'My Custom Label',
          icon: 'MyIcon',
          configured: true,
          actionConfig: { type: 'tool-call' },
        },
      };

      const flow = createTestFlow([node]);
      const serialized = serializeFlow(flow);
      const deserialized = deserializeFlow('flow1', 'Test', 'Draft', serialized);

      expect(deserialized.nodes[0].data?.label).toBe('My Custom Label');
      expect(deserialized.nodes[0].data?.icon).toBe('MyIcon');
    });

    it('uses default label when _label is absent on deserialize', () => {
      const backend: BackendFlowGraph = {
        schema_version: 1,
        id: 'flow1',
        version: 1,
        entry: 'node1',
        nodes: [
          {
            id: 'node1',
            type: 'tool.call',
            config: {},
            // _label is absent
          },
        ],
        edges: [],
        settings: { mode: 'normal', max_hops: 100 },
        metadata: { name: 'Test', description: '', category: '' },
      };

      const deserialized = deserializeFlow('flow1', 'Test', 'Draft', backend);

      expect(deserialized.nodes[0].data?.label).toBe('Call Tool');
    });

    it('uses default icon when _icon is absent on deserialize', () => {
      const backend: BackendFlowGraph = {
        schema_version: 1,
        id: 'flow1',
        version: 1,
        entry: 'node1',
        nodes: [
          {
            id: 'node1',
            type: 'agent.run',
            config: {},
            // _icon is absent
          },
        ],
        edges: [],
        settings: { mode: 'normal', max_hops: 100 },
        metadata: { name: 'Test', description: '', category: '' },
      };

      const deserialized = deserializeFlow('flow1', 'Test', 'Draft', backend);

      expect(deserialized.nodes[0].data?.icon).toBe('Bot');
    });
  });

  describe('Edge cases', () => {
    it('handles empty flow (no nodes)', () => {
      const flow: Flow = {
        id: 'flow1',
        name: 'Empty Flow',
        description: '',
        status: 'draft',
        category: '',
        nodes: [],
        edges: [],
        createdAt: new Date(),
        updatedAt: new Date(),
        version: 1,
      };

      const serialized = serializeFlow(flow);
      expect(serialized.nodes).toEqual([]);
      expect(serialized.edges).toEqual([]);
    });

    it('handles flow with no trigger (entry is empty string)', () => {
      const flow = createTestFlow([
        createActionNode('node1', 'tool-call'),
      ]);

      const serialized = serializeFlow(flow);
      // When no trigger is found, entry should be the first node id or empty
      expect(typeof serialized.entry).toBe('string');
    });

    it('handles node with no config', () => {
      const node: FlowNode = {
        id: 'node1',
        type: 'end',
        position: { x: 0, y: 0 },
        data: {
          nodeType: 'end',
          label: 'End',
          icon: 'CheckCircle2',
          configured: true,
        },
      };

      const flow = createTestFlow([node]);
      const serialized = serializeFlow(flow);

      expect(serialized.nodes[0].config).toEqual({});
    });

    it('handles node with no data', () => {
      const node: FlowNode = {
        id: 'node1',
        type: 'action',
        position: { x: 0, y: 0 },
        data: undefined as any,
      };

      const flow = createTestFlow([node]);
      const serialized = serializeFlow(flow);

      // Node with no data should have empty config
      expect(serialized.nodes[0].config).toEqual({});
    });

    it('handles unknown backend node type on deserialize', () => {
      const backend: BackendFlowGraph = {
        schema_version: 1,
        id: 'flow1',
        version: 1,
        entry: 'node1',
        nodes: [
          {
            id: 'node1',
            type: 'unknown.custom.type',
            config: {},
            _label: 'Unknown Node',
          },
        ],
        edges: [],
        settings: { mode: 'normal', max_hops: 100 },
        metadata: { name: 'Test', description: '', category: '' },
      };

      const deserialized = deserializeFlow('flow1', 'Test', 'Draft', backend);

      // Unknown types should be mapped to 'action'
      expect(deserialized.nodes[0].type).toBe('action');
      // ActionConfig type should map back to 'tool-call' (default)
      expect(deserialized.nodes[0].data?.actionConfig?.type).toBe('tool-call');
    });

    it('handles edges with and without metadata', () => {
      const backend: BackendFlowGraph = {
        schema_version: 1,
        id: 'flow1',
        version: 1,
        entry: 'node1',
        nodes: [
          {
            id: 'node1',
            type: 'tool.call',
            config: {},
          },
          {
            id: 'node2',
            type: 'tool.call',
            config: {},
          },
        ],
        edges: [
          {
            id: 'edge1',
            from: 'node1',
            to: 'node2',
            type: 'always',
            priority: 0,
          },
          {
            id: 'edge2',
            from: 'node2',
            to: 'node1',
            type: 'conditional',
            priority: 1,
            condition: 'x > 5',
            meta: { label: 'Success', custom: 'value' },
          },
        ],
        settings: { mode: 'normal', max_hops: 100 },
        metadata: { name: 'Test', description: '', category: '' },
      };

      const deserialized = deserializeFlow('flow1', 'Test', 'Draft', backend);

      expect(deserialized.edges).toHaveLength(2);
      expect(deserialized.edges[0].label).toBeUndefined();
      expect(deserialized.edges[1].label).toBe('Success');
    });

    it('maps backend status to frontend correctly', () => {
      expect(mapBackendStatusToFrontend('Draft')).toBe('draft');
      expect(mapBackendStatusToFrontend('Active')).toBe('active');
      expect(mapBackendStatusToFrontend('Archived')).toBe('paused');
      expect(mapBackendStatusToFrontend('Unknown')).toBe('draft'); // falls back to draft
    });
  });
});

// ─── Test Helpers ───────────────────────────────────────────────────

function createTestFlow(nodes: FlowNode[]): Flow {
  return {
    id: 'test-flow',
    name: 'Test Flow',
    description: 'A test flow',
    status: 'draft',
    category: 'test',
    nodes,
    edges: [],
    createdAt: new Date(),
    updatedAt: new Date(),
    version: 1,
  };
}

function createActionNode(id: string, type: any): FlowNode {
  return {
    id,
    type: 'action',
    position: { x: 0, y: 0 },
    data: {
      nodeType: 'action',
      label: `${type} Action`,
      icon: 'Play',
      configured: true,
      actionConfig: {
        type,
      },
    },
  };
}

function createActionNodeWithUnmappedType(id: string, type: string): FlowNode {
  return {
    id,
    type: 'action',
    position: { x: 0, y: 0 },
    data: {
      nodeType: 'action',
      label: `${type} Action`,
      icon: 'Play',
      configured: true,
      actionConfig: {
        type,
      } as any,
    },
  };
}
