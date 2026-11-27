/**
 * Built-in step types that have no hand-made form: their settings are drawn by the schema form, like an app's step.
 * Mirrors `KnowledgeSearchNode` and `HandoffNode` in huf/ai/graph/graph_ir.schema.json. The list endpoint returns
 * built-ins only as names, so without these the builder took them for steps of a removed app.
 */
import type { AppNodeType } from '@/services/flow/steps/nodeTypesApi';

export const HUF_APP = 'huf';

export const BUILTIN_SCHEMA_STEPS: AppNodeType[] = [
  {
    type: 'knowledge.search',
    label: 'Search knowledge',
    category: 'agent',
    icon: 'BookOpen',
    description: 'Search a knowledge source and use the best passages.',
    app: HUF_APP,
    config_schema: {
      type: 'object',
      required: ['query', 'knowledge_source'],
      properties: {
        query: { type: 'string', title: 'Search for', description: 'The text to search for.', 'x-huf-widget': 'data-ref' },
        knowledge_source: { type: 'string', title: 'Knowledge source', description: 'The name of the knowledge source to search.' },
        top_k: { type: 'integer', title: 'How many results', description: 'From 1 to 20. Leave empty for 5.' },
      },
    },
  },
  {
    type: 'handoff',
    label: 'Hand to a person',
    category: 'people',
    icon: 'UserRound',
    description: 'Hand the conversation to a person and wait until they hand it back.',
    app: HUF_APP,
    config_schema: {
      type: 'object',
      properties: {
        conversation: { type: 'string', title: 'Conversation', description: 'The conversation to hand over. Or fill in the channel and contact below.', 'x-huf-widget': 'data-ref' },
        gateway: { type: 'string', title: 'Channel', description: 'The channel of the contact.', 'x-huf-widget': 'data-ref' },
        recipient: { type: 'string', title: 'Contact', description: 'The contact whose open conversation is handed over.', 'x-huf-widget': 'data-ref' },
        reason: { type: 'string', title: 'Reason', description: 'Why the conversation is handed over. Kept with the run.' },
        target: { type: 'string', title: 'Hand to', description: 'The queue or person who takes over.' },
        summary: { type: 'string', title: 'Note for the person', description: 'A short note for the person taking over.' },
        priority: { type: 'string', title: 'Priority', enum: ['low', 'normal', 'high', 'urgent'] },
        message: { type: 'string', title: 'Message to the contact', description: 'Sent to the contact when the conversation is handed over.' },
        timeout_ms: { type: 'integer', title: 'Time limit (milliseconds)', description: 'Leave empty to wait until a person hands it back.' },
        timeout_next: { type: 'string', title: 'When time runs out, go to', 'x-huf-widget': 'node' },
      },
    },
  },
];

export const builtinSchemaStep = (type: unknown): AppNodeType | undefined =>
  typeof type === 'string' ? BUILTIN_SCHEMA_STEPS.find((t) => t.type === type) : undefined;
