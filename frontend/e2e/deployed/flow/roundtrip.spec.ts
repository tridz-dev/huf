import { test, expect, Page } from '@playwright/test';
import { FlowsListPage } from './FlowsListPage';
import { FlowCanvasPage } from './FlowCanvasPage';
import { NodeModal } from './NodeModal';
import { ConfigSidebar } from './ConfigSidebar';
import {
  newApiContext,
  deleteFlowByName,
  uniqueFlowName,
  getFlowDefinition,
} from './flowApi';
import type { APIRequestContext } from '@playwright/test';

/**
 * Save/reload round-trip proofs for every node-type config sidebar.
 *
 * Each case builds ONE flow with exactly one instance of the node type
 * under test (plus, for condition/loop, two extra target nodes so their
 * node-id <Select>s have real choices) — this keeps every canvas node's
 * label unique, which matters because FlowCanvas.tsx's action labelMap
 * has no entry for 'condition' or 'http-request' and falls back to the
 * generic string "Action" for both (see KNOWN DEFECT note below); as long
 * as only one such node exists per flow, selectors.canvas.nodeByLabel's
 * exact-text match still resolves unambiguously.
 *
 * Flow per case: Webhook (trigger) -> <node under test> [-> target A -> target B]
 *
 * For every case we: add the node, fill every sidebar field, save, hard
 * reload, reselect the node, and assert every field reads back exactly
 * what was entered. agent-run and condition additionally fetch the
 * persisted Flow Definition doc via the REST API and assert the JSON
 * shape directly, independent of what the UI displays.
 */

const REAL_AGENT = 'Demo Assistant'; // combobox option label rendered as `${agent_name} · ${model}` or bare name
const REAL_ROLE = 'System Manager';
const REAL_DOCTYPE = 'Flow Definition';
const REAL_TOOL = 'add_table_row';

interface Ctx {
  page: Page;
  list: FlowsListPage;
  canvas: FlowCanvasPage;
  modal: NodeModal;
  sidebar: ConfigSidebar;
  flowId: string;
}

async function setupFlow(page: Page, flowName: string): Promise<{ list: FlowsListPage; flowId: string }> {
  const list = new FlowsListPage(page);
  await list.goto();
  const flowId = await list.createFlow(flowName);
  return { list, flowId };
}

async function addWebhookTrigger(canvas: FlowCanvasPage, modal: NodeModal): Promise<void> {
  await canvas.addTrigger();
  await modal.waitForOpen('trigger');
  await modal.selectCard('Webhook');
  await modal.saveTriggerConfiguration();
  await canvas.settle();
}

async function addAction(canvas: FlowCanvasPage, modal: NodeModal, sourceLabel: string, cardName: string): Promise<void> {
  await canvas.addNodeAfter(sourceLabel);
  await modal.waitForOpen('action');
  await modal.selectCard(cardName);
  await canvas.settle();
}

/** Reload the page and reselect a node by its canvas label. */
async function reloadAndReselect(canvas: FlowCanvasPage, label: string): Promise<void> {
  await canvas.reload();
  await canvas.selectNode(label);
}

test.describe('flow node config round-trips (save + hard reload)', () => {
  let api: APIRequestContext;

  test.beforeAll(async ({ baseURL }) => {
    api = await newApiContext(new URL(baseURL!).origin);
  });

  test.afterAll(async () => {
    await api.dispose();
  });

  // ── agent-run ──────────────────────────────────────────────────────
  test('agent-run: all fields round-trip, persisted JSON shape is flat (not nested under input)', async ({ page }) => {
    const flowName = uniqueFlowName('e2e-agentrun');
    const { list, flowId } = await setupFlow(page, flowName);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);
    const sidebar = new ConfigSidebar(page);

    try {
      await addWebhookTrigger(canvas, modal);
      await addAction(canvas, modal, 'Webhook', 'Run Agent');
      await canvas.selectNode('Run Agent');

      await sidebar.fillCombobox('Agent', new RegExp(`^${REAL_AGENT}`));
      await sidebar.fillField('Prompt Template', 'Summarize {{ticket.subject}} for {{customer}}.');
      await sidebar.fillField('Save Response To', 'agent_response');
      await sidebar.fillField('Conversation Mode', 'Isolated (No history)');

      await canvas.save();
      await reloadAndReselect(canvas, 'Run Agent');

      await expect.soft(sidebar.readCombobox('Agent')).resolves.toMatch(new RegExp(`^${REAL_AGENT}`));
      await expect.soft(sidebar.readField('Prompt Template')).resolves.toBe('Summarize {{ticket.subject}} for {{customer}}.');
      await expect.soft(sidebar.readField('Save Response To')).resolves.toBe('agent_response');
      await expect.soft(sidebar.readField('Conversation Mode')).resolves.toBe('Isolated (No history)');

      // API-level shape assertion: does the persisted node.config carry
      // prompt_template flat (matching flow_engine.py's
      // `config.get("prompt_template")` fallback path and
      // flowSerializer.ts's `omitType(actionConfig)`), or has it drifted
      // to a nested `input.prompt_template` shape that only the newer
      // engine code path reads?
      const def = await getFlowDefinition(api, flowId);
      const node = def.definition_json.nodes.find((n) => n.type === 'agent.run');
      expect(node, 'agent.run node missing from persisted definition_json').toBeTruthy();
      const config = node!.config || {};
      expect(config.prompt_template, 'prompt_template should be persisted flat on config, not nested').toBe(
        'Summarize {{ticket.subject}} for {{customer}}.'
      );
      expect((config as Record<string, unknown>).input, 'no nested "input" wrapper expected for this node').toBeUndefined();
      expect(config.conversation_mode).toBe('isolated');
      expect(config.save_response_to_context).toBe('agent_response');
    } finally {
      await deleteFlowByName(api, flowId).catch(() => {});
    }
  });

  // ── tool-call ──────────────────────────────────────────────────────
  // Superseded by fields.spec.ts, which asserts these fields ONE PER TEST.
  // As a single test it set ~8 fields at once, so one bad selector failed the
  // whole node type and told us nothing about the other seven.
  test.skip('tool-call: tool picker, dynamic args, save-result, and attributed agent round-trip', async ({ page }) => {
    const flowName = uniqueFlowName('e2e-toolcall');
    const { flowId } = await setupFlow(page, flowName);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);
    const sidebar = new ConfigSidebar(page);

    try {
      await addWebhookTrigger(canvas, modal);
      await addAction(canvas, modal, 'Webhook', 'Call Tool');
      await canvas.selectNode('Call Tool');

      await sidebar.fillCombobox('Tool', REAL_TOOL);
      // Discover whatever argument fields this tool's parameters render
      // (data-driven — do not hardcode fieldnames from the tool schema).
      await page.waitForTimeout(300); // let getToolFunction() resolve and render the argument block
      const labels = await sidebar.listFieldLabels();
      const argLabels = labels.filter(
        // 'Node Title' renames the NODE, it is not a tool argument - filling it
        // renames the canvas node and every later lookup by label fails.
        (l) => !['Node Title', 'Tool', 'Save Result To Context', 'Attributed Agent (optional)'].includes(l)
      );
      expect(argLabels.length, `expected ${REAL_TOOL} to expose at least one argument field`).toBeGreaterThan(0);
      const argValues: Record<string, string> = {};
      for (const label of argLabels) {
        const value = `e2e-${label.replace(/\s+/g, '_').toLowerCase()}`;
        argValues[label] = value;
        await sidebar.fillField(label, value);
      }
      await sidebar.fillField('Save Result To Context', 'tool_result');
      await sidebar.fillCombobox('Attributed Agent (optional)', new RegExp(`^${REAL_AGENT}`));

      await canvas.save();
      await reloadAndReselect(canvas, 'Call Tool');

      await expect.soft(sidebar.readCombobox('Tool')).resolves.toBe(REAL_TOOL);
      for (const label of argLabels) {
        await expect.soft(sidebar.readField(label)).resolves.toBe(argValues[label]);
      }
      await expect.soft(sidebar.readField('Save Result To Context')).resolves.toBe('tool_result');
      await expect
        .soft(sidebar.readCombobox('Attributed Agent (optional)'))
        .resolves.toMatch(new RegExp(`^${REAL_AGENT}`));
    } finally {
      await deleteFlowByName(api, flowId).catch(() => {});
    }
  });

  // ── router ─────────────────────────────────────────────────────────
  test('router: agent/conversation-mode round-trip; context-injection checkboxes default TRUE and an uncheck survives save+reload', async ({
    page,
  }) => {
    const flowName = uniqueFlowName('e2e-router');
    const { flowId } = await setupFlow(page, flowName);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);
    const sidebar = new ConfigSidebar(page);

    try {
      await addWebhookTrigger(canvas, modal);
      await addAction(canvas, modal, 'Webhook', 'LLM Router');
      await canvas.selectNode('Router');

      // Defaults, untouched: all three must read TRUE.
      await expect.soft(sidebar.isChecked('Include flow context')).resolves.toBe(true);
      await expect.soft(sidebar.isChecked('Include last node result')).resolves.toBe(true);
      await expect.soft(sidebar.isChecked('Include routing candidates')).resolves.toBe(true);

      await sidebar.fillCombobox('Routing Agent', new RegExp(`^${REAL_AGENT}`));
      await sidebar.fillField('Conversation Mode', 'Isolated (No history)');
      await sidebar.setChecked('Include last node result', false); // the one we deliberately flip

      await canvas.save();
      await reloadAndReselect(canvas, 'Router');

      await expect.soft(sidebar.readCombobox('Routing Agent')).resolves.toMatch(new RegExp(`^${REAL_AGENT}`));
      await expect.soft(sidebar.readField('Conversation Mode')).resolves.toBe('Isolated (No history)');
      await expect.soft(sidebar.isChecked('Include flow context')).resolves.toBe(true);
      await expect.soft(sidebar.isChecked('Include last node result')).resolves.toBe(false);
      await expect.soft(sidebar.isChecked('Include routing candidates')).resolves.toBe(true);
    } finally {
      await deleteFlowByName(api, flowId).catch(() => {});
    }
  });

  // ── condition ──────────────────────────────────────────────────────
  test('condition: expression + true/false node Selects round-trip; a deleted target survives as a "Missing node" option', async ({
    page,
  }) => {
    const flowName = uniqueFlowName('e2e-condition');
    const { flowId } = await setupFlow(page, flowName);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);
    const sidebar = new ConfigSidebar(page);

    try {
      await addWebhookTrigger(canvas, modal);
      await addAction(canvas, modal, 'Webhook', 'Condition (If/Else)');
      // KNOWN DEFECT: FlowCanvas.tsx's labelMap has no 'condition' entry,
      // so this node renders with the generic label "Action" instead of
      // something like "Condition". Harmless for this single-node-of-its-
      // kind flow (nodeByLabel('Condition') is still unambiguous), but a real
      // UX bug for a canvas with more than one unmapped action type — see
      // final report.
      await canvas.selectNode('Condition');
      await addAction(canvas, modal, 'Condition', 'Call Tool');
      await addAction(canvas, modal, 'Call Tool', 'Transform Data');

      await canvas.selectNode('Condition');
      await sidebar.fillField('Expression', 'context["status"] == "approved"');
      await sidebar.fillField('True Branch', 'Call Tool');
      await sidebar.fillField('False Branch', 'Transform Data');

      await canvas.save();
      await reloadAndReselect(canvas, 'Condition');

      await expect.soft(sidebar.readField('Expression')).resolves.toBe('context["status"] == "approved"');
      await expect.soft(sidebar.readField('True Branch')).resolves.toBe('Call Tool');
      await expect.soft(sidebar.readField('False Branch')).resolves.toBe('Transform Data');

      // API-level shape assertion for the same node.
      const def1 = await getFlowDefinition(api, flowId);
      const condNode = def1.definition_json.nodes.find((n) => n.type === 'condition');
      expect(condNode, 'condition node missing from persisted definition_json').toBeTruthy();
      expect(condNode!.config?.expression).toBe('context["status"] == "approved"');
      const trueNodeId = condNode!.config?.true_node as string;
      const falseNodeId = condNode!.config?.false_node as string;
      expect(trueNodeId).toBeTruthy();
      expect(falseNodeId).toBeTruthy();

      // Now delete the True-branch target node and prove the reference is
      // preserved (rendered as "Missing node: <id> (not found)"), not
      // silently dropped or nulled out.
      await canvas.deleteNode('Call Tool');
      await canvas.selectNode('Condition');
      await canvas.save();
      await reloadAndReselect(canvas, 'Condition');

      const trueBranchAfterDelete = await sidebar.readField('True Branch');
      expect(trueBranchAfterDelete).toMatch(/^Missing node: .+\(not found\)$/);
      expect(trueBranchAfterDelete).toContain(trueNodeId);
      // False branch (untouched, target still exists) must be unaffected.
      await expect.soft(sidebar.readField('False Branch')).resolves.toBe('Transform Data');

      const def2 = await getFlowDefinition(api, flowId);
      const condNode2 = def2.definition_json.nodes.find((n) => n.type === 'condition');
      expect(
        condNode2!.config?.true_node,
        'true_node reference to the deleted node must be preserved verbatim in persisted JSON, not rewritten to null/empty'
      ).toBe(trueNodeId);
    } finally {
      await deleteFlowByName(api, flowId).catch(() => {});
    }
  });

  // ── loop ───────────────────────────────────────────────────────────
  test('loop: iterate/item/index/max-iterations and loop/done node Selects round-trip; a deleted target survives as "Missing node"', async ({
    page,
  }) => {
    const flowName = uniqueFlowName('e2e-loop');
    const { flowId } = await setupFlow(page, flowName);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);
    const sidebar = new ConfigSidebar(page);

    try {
      await addWebhookTrigger(canvas, modal);
      await addAction(canvas, modal, 'Webhook', 'Loop');
      await addAction(canvas, modal, 'Loop', 'Call Tool');
      await addAction(canvas, modal, 'Call Tool', 'Transform Data');

      await canvas.selectNode('Loop');
      await sidebar.fillField('Iterate Over (Context Key)', 'items');
      await sidebar.fillField('Item Variable', 'current_item');
      await sidebar.fillField('Index Variable', 'current_index');
      await sidebar.fillField('Loop Body Node', 'Call Tool');
      await sidebar.fillField('Done Node', 'Transform Data');
      await sidebar.fillField('Max Iterations', '25');

      await canvas.save();
      await reloadAndReselect(canvas, 'Loop');

      await expect.soft(sidebar.readField('Iterate Over (Context Key)')).resolves.toBe('items');
      await expect.soft(sidebar.readField('Item Variable')).resolves.toBe('current_item');
      await expect.soft(sidebar.readField('Index Variable')).resolves.toBe('current_index');
      await expect.soft(sidebar.readField('Loop Body Node')).resolves.toBe('Call Tool');
      await expect.soft(sidebar.readField('Done Node')).resolves.toBe('Transform Data');
      await expect.soft(sidebar.readField('Max Iterations')).resolves.toBe('25');

      const def = await getFlowDefinition(api, flowId);
      const loopNode = def.definition_json.nodes.find((n) => n.type === 'loop');
      const loopBodyId = loopNode!.config?.loop_node as string;
      expect(loopBodyId).toBeTruthy();

      await canvas.deleteNode('Call Tool');
      await canvas.selectNode('Loop');
      await canvas.save();
      await reloadAndReselect(canvas, 'Loop');

      const loopBodyAfterDelete = await sidebar.readField('Loop Body Node');
      expect(loopBodyAfterDelete).toMatch(/^Missing node: .+\(not found\)$/);
      expect(loopBodyAfterDelete).toContain(loopBodyId);
    } finally {
      await deleteFlowByName(api, flowId).catch(() => {});
    }
  });

  // ── transform ──────────────────────────────────────────────────────
  test('transform: a transformation row (source/target field + operation) round-trips', async ({ page }) => {
    const flowName = uniqueFlowName('e2e-transform');
    const { flowId } = await setupFlow(page, flowName);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);
    const sidebar = new ConfigSidebar(page);

    try {
      await addWebhookTrigger(canvas, modal);
      await addAction(canvas, modal, 'Webhook', 'Transform Data');
      await canvas.selectNode('Transform Data');

      await page.getByRole('button', { name: /add transformation/i }).click();
      // Transformation rows have no field-linking htmlFor/id (their
      // <Label> elements carry no `htmlFor` at all — see report), so we
      // drive them positionally rather than through ConfigSidebar.
      // Take the innermost div that contains BOTH the row heading and inputs.
      // Filtering only on the heading and taking .last() yields the tightest
      // wrapper around the heading itself, which holds no inputs at all.
      const row = page
        .locator('div')
        .filter({ has: page.getByText('Transformation #1', { exact: true }) })
        .filter({ has: page.locator('input') })
        .last();
      await row.locator('input').nth(0).fill('api_response.data');
      await row.locator('input').nth(1).fill('processed_data');
      await row.getByRole('combobox').click();
      await page.getByRole('option', { name: 'Map' }).click();

      await canvas.save();
      await reloadAndReselect(canvas, 'Transform Data');

      const rowAfter = page
        .locator('div')
        .filter({ has: page.getByText('Transformation #1', { exact: true }) })
        .filter({ has: page.locator('input') })
        .last();
      await expect.soft(rowAfter.locator('input').nth(0)).toHaveValue('api_response.data');
      await expect.soft(rowAfter.locator('input').nth(1)).toHaveValue('processed_data');
      await expect.soft(rowAfter.getByRole('combobox')).toHaveText(/Map/);

      const def = await getFlowDefinition(api, flowId);
      const node = def.definition_json.nodes.find((n) => n.type === 'transform');
      const transformations = (node!.config?.transformations as Array<Record<string, unknown>>) || [];
      expect(transformations[0]).toMatchObject({
        source_field: 'api_response.data',
        target_field: 'processed_data',
        operation: 'map',
      });
    } finally {
      await deleteFlowByName(api, flowId).catch(() => {});
    }
  });

  // ── human.approval ─────────────────────────────────────────────────
  // Superseded by fields.spec.ts (one field per test) - see note above.
  test.skip('human.approval: title/instructions/context-summary/approval-type(user)/approver-users/reference/store-key round-trip', async ({
    page,
  }) => {
    const flowName = uniqueFlowName('e2e-humanapproval');
    const { flowId } = await setupFlow(page, flowName);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);
    const sidebar = new ConfigSidebar(page);

    try {
      await addWebhookTrigger(canvas, modal);
      await addAction(canvas, modal, 'Webhook', 'Human in Loop');
      await canvas.selectNode('Human in Loop');

      await sidebar.fillField('Title', 'Approve Invoice #INV-001');
      await sidebar.fillField('Instructions', 'Check totals against the PO before approving.');
      await sidebar.fillField('Context Summary', 'Please review invoice for {{customer}} worth {{amount}}');
      await sidebar.fillField('Approval Type', 'By User');
      await sidebar.fillField('Approver Users (comma-separated emails)', 'manager@company.com, cfo@company.com');
      await sidebar.fillCombobox('Reference DocType (Optional)', REAL_DOCTYPE);
      await sidebar.fillField('Reference Document Name', '{{invoice.name}}');
      await sidebar.fillField('Store Decision in Context Key', 'approval_result');

      await canvas.save();
      await reloadAndReselect(canvas, 'Human in Loop');

      await expect.soft(sidebar.readField('Title')).resolves.toBe('Approve Invoice #INV-001');
      await expect.soft(sidebar.readField('Instructions')).resolves.toBe('Check totals against the PO before approving.');
      await expect
        .soft(sidebar.readField('Context Summary'))
        .resolves.toBe('Please review invoice for {{customer}} worth {{amount}}');
      await expect.soft(sidebar.readField('Approval Type')).resolves.toBe('By User');
      await expect
        .soft(sidebar.readField('Approver Users (comma-separated emails)'))
        .resolves.toBe('manager@company.com, cfo@company.com');
      await expect.soft(sidebar.readCombobox('Reference DocType (Optional)')).resolves.toBe(REAL_DOCTYPE);
      await expect.soft(sidebar.readField('Reference Document Name')).resolves.toBe('{{invoice.name}}');
      await expect.soft(sidebar.readField('Store Decision in Context Key')).resolves.toBe('approval_result');
    } finally {
      await deleteFlowByName(api, flowId).catch(() => {});
    }
  });

  // ── http-request ───────────────────────────────────────────────────
  test('http-request: url/method/headers(JSON)/body(JSON)/timeout/save-result round-trip', async ({ page }) => {
    const flowName = uniqueFlowName('e2e-httprequest');
    const { flowId } = await setupFlow(page, flowName);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);
    const sidebar = new ConfigSidebar(page);

    try {
      await addWebhookTrigger(canvas, modal);
      await addAction(canvas, modal, 'Webhook', 'HTTP Request');
      // KNOWN DEFECT (same root cause as condition, see above): no
      // labelMap entry for 'http-request' either, so this too renders as
      // the generic "Action" label.
      await canvas.selectNode('HTTP Request');

      await sidebar.fillField('URL', 'https://api.example.com/endpoint');
      await sidebar.fillField('Method', 'POST');
      await sidebar.fillField('Headers (JSON)', '{\n  "Authorization": "Bearer {{token}}"\n}');
      await sidebar.fillField('Body', '{\n  "key": "{{context.value}}"\n}');
      await sidebar.fillField('Timeout (seconds)', '45');
      await sidebar.fillField('Save Result To Context', 'api_response');

      await canvas.save();
      await reloadAndReselect(canvas, 'HTTP Request');

      await expect.soft(sidebar.readField('URL')).resolves.toBe('https://api.example.com/endpoint');
      await expect.soft(sidebar.readField('Method')).resolves.toBe('POST');
      const headers = await sidebar.readField('Headers (JSON)');
      expect(JSON.parse(headers)).toEqual({ Authorization: 'Bearer {{token}}' });
      const body = await sidebar.readField('Body');
      expect(JSON.parse(body)).toEqual({ key: '{{context.value}}' });
      await expect.soft(sidebar.readField('Timeout (seconds)')).resolves.toBe('45');
      await expect.soft(sidebar.readField('Save Result To Context')).resolves.toBe('api_response');
    } finally {
      await deleteFlowByName(api, flowId).catch(() => {});
    }
  });
});
