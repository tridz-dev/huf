import type { BackendFlowGraph } from '@/services/flowApi';
import type { FlowCardStep } from '@/services/flowCardsApi';

/**
 * Templates for "New flow" (UX-20). A STATIC catalog that ships with the app, in the same graph format a saved flow
 * uses, so it works on every site with no set-up script and is reviewed and versioned with the code.
 *
 * Where they come from: the small "Huf Demo" flows (docs/flow/DEMO_FLOWS.md) with everything that belonged to the
 * test site taken out: webhook secrets (the server makes a fresh one for every copy), the Slack channel, the
 * e-mail address and the agent name (the server picks one of the site's agents, or asks the person to create one),
 * and with plain step names. Picking a template calls `create_flow_from_template`, which makes a NEW draft: a
 * unique name, a new secret, and a list of steps that still need setup.
 *
 * To add one: author it in the editor, copy its definition (View as JSON), delete secrets and anything specific to
 * your site, and add it here. The test in flowTemplates.test.ts checks the shape.
 */
export interface FlowTemplate {
  id: string;
  name: string;
  /** One plain line about what it does. */
  description: string;
  /** Heading it appears under in the chooser. */
  group: 'Starter' | 'AI' | 'People' | 'Connected apps';
  graph: BackendFlowGraph;
}

export const FLOW_TEMPLATES: FlowTemplate[] = [
  {
    id: 'reply-to-request',
    name: 'Reply to a web request',
    description: 'Send a name to a web address and get it back in capital letters.',
    group: 'Starter',
    graph: {
      schema_version: '1.0.0',
      profile: 'flow',
      fingerprint: '0000000000000000000000000000000000000000000000000000000000000000',
      entry: ['empty_trigger'],
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger.webhook',
          config: { method: 'POST' },
          next: 'node_1793273055812',
          _label: 'Webhook',
          _position: { x: 250, y: 100 },
        },
        {
          id: 'node_1793273055812',
          type: 'transform',
          config: { op: 'upper', input: { text: { $from: 'input.name' } } },
          next: 'node_1793273057245',
          _label: 'Shout',
          _position: { x: 250, y: 250 },
        },
        {
          id: 'node_1793273057245',
          type: 'output',
          config: { value: { $from: 'node_1793273055812' } },
          _label: 'Result',
          _position: { x: 250, y: 400 },
        },
      ],
      contract: {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
        limits: {
          max_nodes: 200,
          max_rows: 10000,
          max_output_bytes: 1000000,
          max_parallel_calls: 4,
          max_foreach_iterations: 1000,
          max_external_calls: 200,
          max_writes: 100,
          max_wall_time_ms: 300000,
          fail_closed: true,
        },
      },
    } as unknown as BackendFlowGraph,
  },
  {
    id: 'big-or-small',
    name: 'Split orders into big and small',
    description: 'Check an amount and take one path for big orders and another for small ones.',
    group: 'Starter',
    graph: {
      schema_version: '1.0.0',
      profile: 'flow',
      fingerprint: '0000000000000000000000000000000000000000000000000000000000000000',
      entry: ['empty_trigger'],
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger.webhook',
          config: { method: 'POST' },
          next: 'node_1793273064624',
          _label: 'Webhook',
          _position: { x: 250, y: 100 },
        },
        {
          id: 'node_1793273064624',
          type: 'condition',
          config: {
            expression: "input['amount'] > 100",
            on_true: 'node_1793273065231',
            on_false: 'node_1793273065840',
          },
          _label: 'Big order?',
          _position: { x: 250, y: 250 },
        },
        {
          id: 'node_1793273065231',
          type: 'output',
          config: { value: 'Big order' },
          _label: 'Big order',
          _position: { x: 130, y: 400 },
        },
        {
          id: 'node_1793273065840',
          type: 'output',
          config: { value: 'Small order' },
          _label: 'Small order',
          _position: { x: 370, y: 400 },
        },
      ],
      contract: {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
        limits: {
          max_nodes: 200,
          max_rows: 10000,
          max_output_bytes: 1000000,
          max_parallel_calls: 4,
          max_foreach_iterations: 1000,
          max_external_calls: 200,
          max_writes: 100,
          max_wall_time_ms: 300000,
          fail_closed: true,
        },
      },
    } as unknown as BackendFlowGraph,
  },
  {
    id: 'each-item',
    name: 'Do something for every item',
    description: 'Go through a list one item at a time and collect the results.',
    group: 'Starter',
    graph: {
      schema_version: '1.0.0',
      profile: 'flow',
      fingerprint: '0000000000000000000000000000000000000000000000000000000000000000',
      entry: ['empty_trigger'],
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger.webhook',
          config: { method: 'POST' },
          next: 'node_1793273075737',
          _label: 'Webhook',
          _position: { x: 250, y: 100 },
        },
        {
          id: 'node_1793273075737',
          type: 'foreach',
          config: {
            items: { $from: 'input.items' },
            max_iterations: 20,
            on_item_error: 'skip',
            collect: { $from: 'node_1793273076346' },
            body: ['node_1793273076346'],
          },
          next: 'node_1793273077758',
          _label: 'For each item',
          _position: { x: 250, y: 250 },
        },
        {
          id: 'node_1793273076346',
          type: 'transform',
          config: { op: 'upper', input: { text: { $from: 'foreach.item' } } },
          _label: 'Shout item',
          _position: { x: 130, y: 400 },
        },
        {
          id: 'node_1793273077758',
          type: 'output',
          config: { value: { $from: 'node_1793273075737' } },
          _label: 'All done',
          _position: { x: 370, y: 400 },
        },
      ],
      contract: {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
        limits: {
          max_nodes: 200,
          max_rows: 10000,
          max_output_bytes: 1000000,
          max_parallel_calls: 4,
          max_foreach_iterations: 1000,
          max_external_calls: 200,
          max_writes: 100,
          max_wall_time_ms: 300000,
          fail_closed: true,
        },
      },
    } as unknown as BackendFlowGraph,
  },
  {
    id: 'clean-and-total',
    name: 'Clean up and total your data',
    description: 'Tidy a name, keep the orders above 100 and add them up.',
    group: 'Starter',
    graph: {
      schema_version: '1.0.0',
      profile: 'flow',
      fingerprint: '0000000000000000000000000000000000000000000000000000000000000000',
      entry: ['empty_trigger'],
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger.webhook',
          config: { method: 'POST' },
          next: 'node_1793273086417',
          _label: 'Webhook',
          _position: { x: 250, y: 100 },
        },
        {
          id: 'node_1793273086417',
          type: 'transform',
          config: { op: 'trim', input: { text: { $from: 'input.name' } } },
          next: 'node_1793273087880',
          _label: 'Clean name',
          _position: { x: 250, y: 250 },
        },
        {
          id: 'node_1793273087880',
          type: 'transform',
          config: { op: 'upper', input: { text: { $from: 'node_1793273086417' } } },
          next: 'node_1793273089312',
          _label: 'Shout',
          _position: { x: 250, y: 400 },
        },
        {
          id: 'node_1793273089312',
          type: 'transform',
          config: { op: 'filter', input: { rows: { $from: 'input.orders' }, where: "row['amount'] > 100" } },
          next: 'node_1793273090862',
          _label: 'Big orders',
          _position: { x: 250, y: 550 },
        },
        {
          id: 'node_1793273090862',
          type: 'transform',
          config: { op: 'aggregate', input: { rows: { $from: 'node_1793273089312' }, op: 'sum', field: 'amount' } },
          next: 'node_1793273092378',
          _label: 'Total',
          _position: { x: 250, y: 700 },
        },
        {
          id: 'node_1793273092378',
          type: 'output',
          config: { value: null },
          _label: 'Finish',
          _position: { x: 250, y: 850 },
        },
      ],
      contract: {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
        limits: {
          max_nodes: 200,
          max_rows: 10000,
          max_output_bytes: 1000000,
          max_parallel_calls: 4,
          max_foreach_iterations: 1000,
          max_external_calls: 200,
          max_writes: 100,
          max_wall_time_ms: 300000,
          fail_closed: true,
        },
      },
    } as unknown as BackendFlowGraph,
  },
  {
    id: 'ask-agent',
    name: 'Ask an AI agent',
    description: 'Give an AI agent a task and use its answer.',
    group: 'AI',
    graph: {
      schema_version: '1.0.0',
      profile: 'flow',
      fingerprint: '0000000000000000000000000000000000000000000000000000000000000000',
      entry: ['empty_trigger'],
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger.webhook',
          config: { method: 'POST' },
          next: 'node_1793273099201',
          _label: 'Webhook',
          _position: { x: 250, y: 100 },
        },
        {
          id: 'node_1793273099201',
          type: 'agent.run',
          config: {
            agent: '',
            prompt: 'Write one short friendly greeting for this person: {input}',
            prompt_bindings: { input: { $from: 'input' } },
          },
          next: 'node_1793273100575',
          _label: 'Greeter',
          _position: { x: 250, y: 250 },
        },
        {
          id: 'node_1793273100575',
          type: 'output',
          config: { value: { $from: 'node_1793273099201' } },
          _label: 'Reply',
          _position: { x: 250, y: 400 },
        },
      ],
      contract: {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
        limits: {
          max_nodes: 200,
          max_rows: 10000,
          max_output_bytes: 1000000,
          max_parallel_calls: 4,
          max_foreach_iterations: 1000,
          max_external_calls: 200,
          max_writes: 100,
          max_wall_time_ms: 300000,
          fail_closed: true,
        },
      },
    } as unknown as BackendFlowGraph,
  },
  {
    id: 'ai-picks-path',
    name: 'Let AI pick the path',
    description: 'An AI model reads a message and decides if it is urgent or routine.',
    group: 'AI',
    graph: {
      schema_version: '1.0.0',
      profile: 'flow',
      fingerprint: '0000000000000000000000000000000000000000000000000000000000000000',
      entry: ['empty_trigger'],
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger.webhook',
          config: { method: 'POST' },
          next: 'node_1793273112289',
          _label: 'Webhook',
          _position: { x: 250, y: 100 },
        },
        {
          id: 'node_1793273112289',
          type: 'router.llm',
          config: {
            prompt: 'Is this message urgent or routine? Message: {input}',
            options: [
              { label: 'urgent', node_id: 'node_1793273113197' },
              { label: 'routine', node_id: 'node_1793273114587' },
            ],
            default: 'node_1793273114587',
          },
          _label: 'Triage',
          _position: { x: 250, y: 250 },
        },
        {
          id: 'node_1793273113197',
          type: 'transform',
          config: { op: 'upper', input: { text: { $from: 'input.text' } } },
          next: 'node_1793273114587',
          _label: 'Escalate',
          _position: { x: 250, y: 400 },
        },
        {
          id: 'node_1793273114587',
          type: 'transform',
          config: { op: 'lower', input: { text: { $from: 'input.text' } } },
          _label: 'Log request',
          _position: { x: 530, y: 550 },
        },
      ],
      contract: {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
        limits: {
          max_nodes: 200,
          max_rows: 10000,
          max_output_bytes: 1000000,
          max_parallel_calls: 4,
          max_foreach_iterations: 1000,
          max_external_calls: 200,
          max_writes: 100,
          max_wall_time_ms: 300000,
          fail_closed: true,
        },
      },
    } as unknown as BackendFlowGraph,
  },
  {
    id: 'ask-approval',
    name: 'Ask a person to approve',
    description: 'Pause until someone approves or rejects, then follow that path.',
    group: 'People',
    graph: {
      schema_version: '1.0.0',
      profile: 'flow',
      fingerprint: '0000000000000000000000000000000000000000000000000000000000000000',
      entry: ['empty_trigger'],
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger.webhook',
          config: { method: 'POST' },
          next: 'node_1793273125361',
          _label: 'Webhook',
          _position: { x: 250, y: 100 },
        },
        {
          id: 'node_1793273125361',
          type: 'human.approval',
          config: {
            message: 'Approve this order: {input}',
            approver_type: 'role',
            approver_role: 'Huf User',
            approve_next: 'node_1793273127004',
            reject_next: 'node_1793273127604',
          },
          _label: 'Wait for approval',
          _position: { x: 250, y: 250 },
        },
        {
          id: 'node_1793273127004',
          type: 'output',
          config: { value: 'approved' },
          _label: 'Approved',
          _position: { x: 130, y: 400 },
        },
        {
          id: 'node_1793273127604',
          type: 'output',
          config: { value: 'rejected' },
          _label: 'Rejected',
          _position: { x: 370, y: 400 },
        },
      ],
      contract: {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
        limits: {
          max_nodes: 200,
          max_rows: 10000,
          max_output_bytes: 1000000,
          max_parallel_calls: 4,
          max_foreach_iterations: 1000,
          max_external_calls: 200,
          max_writes: 100,
          max_wall_time_ms: 300000,
          fail_closed: true,
        },
      },
    } as unknown as BackendFlowGraph,
  },
  {
    id: 'fetch-page',
    name: 'Fetch a web page',
    description: 'Ask a web address for its content when the flow starts.',
    group: 'Starter',
    graph: {
      schema_version: '1.0.0',
      profile: 'flow',
      fingerprint: '0000000000000000000000000000000000000000000000000000000000000000',
      entry: ['empty_trigger'],
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger.webhook',
          config: { method: 'POST' },
          next: 'node_1793273133076',
          _label: 'Webhook',
          _position: { x: 250, y: 100 },
        },
        {
          id: 'node_1793273133076',
          type: 'tool.call',
          config: { tool_id: 'http_request', input: { url: 'https://example.com', method: 'GET' } },
          next: 'node_1793273133665',
          _label: 'HTTP Request',
          _position: { x: 250, y: 250 },
        },
        {
          id: 'node_1793273133665',
          type: 'output',
          config: { value: null },
          _label: 'Finish',
          _position: { x: 250, y: 400 },
        },
      ],
      contract: {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: ['http_request'], code: 'none' },
        limits: {
          max_nodes: 200,
          max_rows: 10000,
          max_output_bytes: 1000000,
          max_parallel_calls: 4,
          max_foreach_iterations: 1000,
          max_external_calls: 200,
          max_writes: 100,
          max_wall_time_ms: 300000,
          fail_closed: true,
        },
      },
    } as unknown as BackendFlowGraph,
  },
  {
    id: 'every-hour',
    name: 'Do something every hour',
    description: 'Start by itself on a schedule, no one has to press a button.',
    group: 'Starter',
    graph: {
      schema_version: '1.0.0',
      profile: 'flow',
      fingerprint: '0000000000000000000000000000000000000000000000000000000000000000',
      entry: ['empty_trigger'],
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger.schedule',
          config: { cron: '0 */1 * * *' },
          next: 'node_1793273153072',
          _label: 'Schedule',
          _position: { x: 250, y: 100 },
        },
        {
          id: 'node_1793273153072',
          type: 'tool.call',
          config: { tool_id: 'http_request', input: { url: 'https://example.com', method: 'GET' } },
          next: 'node_1793273153643',
          _label: 'HTTP Request',
          _position: { x: 250, y: 250 },
        },
        {
          id: 'node_1793273153643',
          type: 'output',
          config: { value: null },
          _label: 'Finish',
          _position: { x: 250, y: 400 },
        },
      ],
      contract: {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: ['http_request'], code: 'none' },
        limits: {
          max_nodes: 200,
          max_rows: 10000,
          max_output_bytes: 1000000,
          max_parallel_calls: 4,
          max_foreach_iterations: 1000,
          max_external_calls: 200,
          max_writes: 100,
          max_wall_time_ms: 300000,
          fail_closed: true,
        },
      },
    } as unknown as BackendFlowGraph,
  },
  {
    id: 'record-created',
    name: 'React when a record is created',
    description: 'Start when a new ToDo is added and use what was written in it.',
    group: 'Starter',
    graph: {
      schema_version: '1.0.0',
      profile: 'flow',
      fingerprint: '0000000000000000000000000000000000000000000000000000000000000000',
      entry: ['empty_trigger'],
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger.doc-event',
          config: { doctype: 'ToDo', event: 'after_insert' },
          next: 'node_1793273159294',
          _label: 'Data',
          _position: { x: 250, y: 100 },
        },
        {
          id: 'node_1793273159294',
          type: 'transform',
          config: { op: 'upper', input: { text: { $from: 'input.description' } } },
          next: 'node_1793273160662',
          _label: 'Shout',
          _position: { x: 250, y: 250 },
        },
        {
          id: 'node_1793273160662',
          type: 'output',
          config: { value: null },
          _label: 'Finish',
          _position: { x: 250, y: 400 },
        },
      ],
      contract: {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
        limits: {
          max_nodes: 200,
          max_rows: 10000,
          max_output_bytes: 1000000,
          max_parallel_calls: 4,
          max_foreach_iterations: 1000,
          max_external_calls: 200,
          max_writes: 100,
          max_wall_time_ms: 300000,
          fail_closed: true,
        },
      },
    } as unknown as BackendFlowGraph,
  },
  {
    id: 'post-to-slack',
    name: 'Post a message to Slack',
    description: 'Send a message to a Slack channel. Needs Slack to be connected.',
    group: 'Connected apps',
    graph: {
      schema_version: '1.0.0',
      profile: 'flow',
      fingerprint: '0000000000000000000000000000000000000000000000000000000000000000',
      entry: ['empty_trigger'],
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger.webhook',
          config: { method: 'POST' },
          next: 'node_1793273141883',
          _label: 'Webhook',
          _position: { x: 250, y: 100 },
        },
        {
          id: 'node_1793273141883',
          type: 'tool.call',
          config: { tool_id: 'slack_send_message', input: { channel: '', text: 'Hello from Huf' } },
          next: 'node_1793273142494',
          _label: 'Slack',
          _position: { x: 250, y: 250 },
        },
        {
          id: 'node_1793273142494',
          type: 'output',
          config: { value: null },
          _label: 'Finish',
          _position: { x: 250, y: 400 },
        },
      ],
      contract: {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
        limits: {
          max_nodes: 200,
          max_rows: 10000,
          max_output_bytes: 1000000,
          max_parallel_calls: 4,
          max_foreach_iterations: 1000,
          max_external_calls: 200,
          max_writes: 100,
          max_wall_time_ms: 300000,
          fail_closed: true,
        },
      },
    } as unknown as BackendFlowGraph,
  },
  {
    id: 'send-email',
    name: 'Send an email',
    description: 'Send an email through Gmail. Needs Gmail to be connected.',
    group: 'Connected apps',
    graph: {
      schema_version: '1.0.0',
      profile: 'flow',
      fingerprint: '0000000000000000000000000000000000000000000000000000000000000000',
      entry: ['empty_trigger'],
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger.webhook',
          config: { method: 'POST' },
          next: 'node_1793273147331',
          _label: 'Webhook',
          _position: { x: 250, y: 100 },
        },
        {
          id: 'node_1793273147331',
          type: 'tool.call',
          config: {
            tool_id: 'gmail_send_email',
            input: { to: '', subject: 'Hello from Huf', body: 'This is a message sent by a Huf flow.' },
          },
          next: 'node_1793273147933',
          _label: 'Send email',
          _position: { x: 250, y: 250 },
        },
        {
          id: 'node_1793273147933',
          type: 'output',
          config: { value: null },
          _label: 'Finish',
          _position: { x: 250, y: 400 },
        },
      ],
      contract: {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
        limits: {
          max_nodes: 200,
          max_rows: 10000,
          max_output_bytes: 1000000,
          max_parallel_calls: 4,
          max_foreach_iterations: 1000,
          max_external_calls: 200,
          max_writes: 100,
          max_wall_time_ms: 300000,
          fail_closed: true,
        },
      },
    } as unknown as BackendFlowGraph,
  },
];

/** The steps after the trigger, in the order the template lists them (for the icon strip). */
export function templateSteps(template: FlowTemplate): FlowCardStep[] {
  return template.graph.nodes
    .filter((n) => !n.type.startsWith('trigger.'))
    .map((n) => {
      const toolId = n.type === 'tool.call' && typeof n.config.tool_id === 'string' ? n.config.tool_id : undefined;
      return toolId ? { type: n.type, tool_id: toolId } : { type: n.type };
    });
}

/** Type of the trigger a template starts with: webhook, schedule or doc-event. */
export function templateTrigger(template: FlowTemplate): 'webhook' | 'schedule' | 'doc-event' {
  const trigger = template.graph.nodes.find((n) => n.type.startsWith('trigger.'));
  return (trigger?.type.split('.')[1] ?? 'webhook') as 'webhook' | 'schedule' | 'doc-event';
}

export const TEMPLATE_GROUPS: FlowTemplate['group'][] = ['Starter', 'AI', 'People', 'Connected apps'];
