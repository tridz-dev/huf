import catalog from './flowTemplates.json';
import type { BackendFlowGraph } from '@/services/flowApi';
import type { FlowCardStep } from '@/services/flow/flowCardsApi';

/**
 * Templates for "New flow" (UX-20). A STATIC catalog (flowTemplates.json, next to this file) that ships with the app, in the same graph format a saved flow
 * uses, so it works on every site with no set-up script and is reviewed and versioned with the code.
 *
 * Where they come from: the small "Huf Demo" flows (docs/flow/DEMO_FLOWS.md) with everything that belonged to the
 * test site taken out: webhook secrets (the server makes a fresh one for every copy), the Slack channel, the
 * e-mail address and the agent name (the server picks one of the site's agents, or asks the person to create one),
 * and with plain step names. Picking a template calls `create_flow_from_template`, which makes a NEW draft: a
 * unique name, a new secret, and a list of steps that still need setup.
 *
 * To add one: author it in the editor, copy its definition (View as JSON), delete secrets and anything specific to
 * your site, and add it to the JSON. The test in flowTemplates.test.ts checks the shape.
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

export const FLOW_TEMPLATES = catalog as unknown as FlowTemplate[];

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
