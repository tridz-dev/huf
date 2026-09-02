import { test, expect, Page } from '@playwright/test';
import { FlowsListPage } from './FlowsListPage';
import { FlowCanvasPage } from './FlowCanvasPage';
import { NodeModal } from './NodeModal';
import { ConfigSidebar } from './ConfigSidebar';
import { newApiContext, uniqueFlowName, getFlowDefinition } from './flowApi';

/**
 * Point 8 — exhaustive per-field round-trip coverage for the two node types
 * that were only sampled in fields.spec.ts: `agent-run` ("Run Agent") and
 * `router` ("LLM Router").
 *
 * Field inventory, read directly from RightSidebar.tsx:
 *
 * agent-run (config.type === 'agent-run', lines ~672-728):
 *   - Label "Agent"               -> Combobox    -> config.agent_name
 *   - Label "Prompt Template"     -> textarea     -> config.prompt_template
 *   - Label "Save Response To"    -> Input        -> config.save_response_to_context
 *   - Label "Conversation Mode"   -> Select       -> config.conversation_mode
 *       (id="agent-run-conv-mode"; options "Flow Shared (Default)" / "Isolated (No history)")
 *
 * router (config.type === 'router', lines ~855-935):
 *   - Label "Routing Agent"                 -> Combobox -> config.router_agent_name
 *   - Label "Conversation Mode"             -> Select   -> config.conversation_mode
 *       (id="conv-mode"; same two options as agent-run)
 *   - Label "Include flow context"          -> Checkbox -> config.inject.include_context (default true)
 *   - Label "Include last node result"      -> Checkbox -> config.inject.include_last_node_result (default true)
 *   - Label "Include routing candidates"    -> Checkbox -> config.inject.include_candidates (default true)
 *
 * All three router checkboxes write into a NESTED `inject: {...}` object
 * (handleUpdateActionConfig('inject', { ...inject, [field]: value })), which
 * is exactly the flat-vs-nested shape bug class this track exists to catch —
 * so those three tests assert the persisted JSON shape via getFlowDefinition,
 * not just what the UI reads back.
 */

async function buildNodeFlow(page: Page, card: string, prefix: string) {
  const list = new FlowsListPage(page);
  const canvas = new FlowCanvasPage(page);
  const modal = new NodeModal(page);
  const flowId = await list.createFlow(uniqueFlowName(prefix));
  await canvas.addTrigger();
  await modal.waitForOpen('trigger');
  await modal.selectCard('Webhook');
  await modal.saveTriggerConfiguration();
  await canvas.settle();
  await canvas.addNodeAfter('Webhook');
  await modal.waitForOpen('action');
  await modal.selectCard(card);
  await canvas.settle();
  return { canvas, flowId, sidebar: new ConfigSidebar(page) };
}

/** Fill one text/textarea field via ConfigSidebar.fillField, save, hard-reload, and assert it round-trips. */
function roundTripField(
  card: string,
  nodeLabel: string,
  prefix: string,
  label: string,
  value: string,
) {
  test(`${card}: "${label}" round-trips`, async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlow(page, card, prefix);
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode(nodeLabel);
      await sidebar.fillField(label, value);
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      // Re-select by POSITION, not by label: see fields.spec.ts for why.
      await page.locator('.react-flow__node').nth(1).click();
      const got = (await sidebar.readField(label)).replace(/\s*,\s*/g, ',').trim();
      expect(got).toBe(value.replace(/\s*,\s*/g, ',').trim());
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
}

/** Fill a Combobox-driven field, save, hard-reload, and assert it round-trips. */
function roundTripCombobox(
  card: string,
  nodeLabel: string,
  prefix: string,
  label: string,
  optionText: string,
) {
  test(`${card}: "${label}" (combobox) round-trips`, async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlow(page, card, prefix);
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode(nodeLabel);
      await sidebar.fillCombobox(label, optionText);
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await page.locator('.react-flow__node').nth(1).click();
      const got = await sidebar.readCombobox(label);
      expect(got).toContain(optionText);
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
}

/**
 * Uncheck one of the router's context-injection checkboxes, save, hard-reload,
 * and assert BOTH that the UI still reads it unchecked AND that the persisted
 * JSON carries it inside a nested `inject: {...}` object (the shape
 * huf/ai/flow_orchestrator.py actually reads) rather than flattened onto the
 * node config.
 */
function roundTripInjectCheckbox(label: string, injectKey: string) {
  test(`router: "${label}" checkbox (inject.${injectKey}) round-trips, default true, nested shape persisted`, async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlow(page, 'LLM Router', 'rt-router-inject');
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode('Router');

      // Default is checked (true) per flow_orchestrator.py's default.
      expect(await sidebar.isChecked(label)).toBe(true);

      await sidebar.setChecked(label, false);
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await page.locator('.react-flow__node').nth(1).click();

      expect(await sidebar.isChecked(label)).toBe(false);

      // Assert the persisted shape directly: it must be nested under
      // `inject`, not a flat top-level key — this is the exact class of
      // bug (flat vs nested `prompt_template`) this track exists for.
      const def = await getFlowDefinition(api, flowId);
      const routerNode = def.definition_json.nodes.find((n) => n.type === 'router.llm');
      expect(routerNode).toBeTruthy();
      const config = (routerNode!.config ?? {}) as Record<string, unknown>;
      expect(config[injectKey]).toBeUndefined(); // never flattened onto the node config
      const inject = config.inject as Record<string, unknown> | undefined;
      expect(inject).toBeTruthy();
      expect(inject![injectKey]).toBe(false);
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
}

test.describe('per-field config round-trip: agent-run and router', () => {
  // --- agent-run ---
  roundTripCombobox('Run Agent', 'Run Agent', 'rt-agentrun', 'Agent', 'Demo Assistant');
  roundTripField('Run Agent', 'Run Agent', 'rt-agentrun', 'Prompt Template', 'Summarize {{context.input}} for the user.');
  roundTripField('Run Agent', 'Run Agent', 'rt-agentrun', 'Save Response To', 'agent_response');
  roundTripField('Run Agent', 'Run Agent', 'rt-agentrun', 'Conversation Mode', 'Isolated (No history)');

  // --- router ---
  roundTripCombobox('LLM Router', 'Router', 'rt-router', 'Routing Agent', 'Demo Assistant');
  roundTripField('LLM Router', 'Router', 'rt-router', 'Conversation Mode', 'Isolated (No history)');

  // --- router context-injection checkboxes (nested `inject: {...}` shape) ---
  roundTripInjectCheckbox('Include flow context', 'include_context');
  roundTripInjectCheckbox('Include last node result', 'include_last_node_result');
  roundTripInjectCheckbox('Include routing candidates', 'include_candidates');
});
