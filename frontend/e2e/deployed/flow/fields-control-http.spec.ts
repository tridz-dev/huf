import { test, expect, Page } from '@playwright/test';
import { FlowsListPage } from './FlowsListPage';
import { FlowCanvasPage } from './FlowCanvasPage';
import { NodeModal } from './NodeModal';
import { ConfigSidebar } from './ConfigSidebar';
import { newApiContext, uniqueFlowName } from './flowApi';

/**
 * Point 8 — exhaustive per-field round-trip coverage for the three
 * remaining node types that fields.spec.ts didn't cover: condition, loop,
 * and http-request. Same rationale as fields.spec.ts: one field per test,
 * so a single bad selector names exactly which control is broken instead
 * of failing the whole node type.
 *
 * Node-reference pickers (true_node/false_node/loop_node/done_node) get
 * dedicated tests beyond plain round-trip: option-list correctness,
 * self-exclusion, and — the highest-value assertion here — that a saved
 * reference to a since-deleted node is preserved and rendered as a
 * "Missing node" option rather than silently dropped (see
 * RightSidebar.tsx's renderNodeIdSelect, which special-cases exactly this).
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
  return { canvas, modal, flowId, sidebar: new ConfigSidebar(page) };
}

/**
 * Same as buildNodeFlow, but also adds two downstream target nodes after
 * the node under test, so its node-id <Select>s (true/false/loop/done)
 * have real canvas nodes to choose from. Mirrors roundtrip.spec.ts's
 * condition/loop setup.
 *
 * KNOWN DEFECT (documented in roundtrip.spec.ts): FlowCanvas.tsx's action
 * labelMap has no entry for 'condition' or 'http-request', so both render
 * with the generic canvas label "Action" rather than something type-specific.
 * Harmless here because only one such node exists per flow.
 */
async function buildNodeFlowWithTargets(page: Page, card: string, nodeCanvasLabel: string, prefix: string) {
  const built = await buildNodeFlow(page, card, prefix);
  const { canvas, modal } = built;
  await canvas.selectNode(nodeCanvasLabel);
  await canvas.addNodeAfter(nodeCanvasLabel);
  await modal.waitForOpen('action');
  await modal.selectCard('Call Tool');
  await canvas.settle();
  await canvas.addNodeAfter('Call Tool');
  await modal.waitForOpen('action');
  await modal.selectCard('Transform Data');
  await canvas.settle();
  return built;
}

/** Fill one field, save, hard-reload, and assert it came back unchanged. */
function roundTripField(
  card: string,
  nodeLabel: string,
  prefix: string,
  label: string,
  value: string,
  pre?: (sidebar: ConfigSidebar, canvas: FlowCanvasPage, modal: NodeModal) => Promise<void>,
) {
  test(`${card}: "${label}" round-trips`, async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlow(page, card, prefix);
      flowId = built.flowId;
      const { canvas, sidebar, modal } = built;
      await canvas.selectNode(nodeLabel);
      if (pre) await pre(sidebar, canvas, modal);
      await sidebar.fillField(label, value);
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      // Re-select by POSITION: node 0 is the trigger, node 1 is the action
      // node under test.
      await page.locator('.react-flow__node').nth(1).click();
      const got = (await sidebar.readField(label)).replace(/\s*,\s*/g, ',').trim();
      expect(got).toBe(value.replace(/\s*,\s*/g, ',').trim());
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
}

/**
 * Round-trip for a node-reference picker field. Needs downstream target
 * nodes to exist, so it can't reuse the plain buildNodeFlow above; picks
 * "Call Tool" as the target since it's a stable, unambiguous canvas label.
 */
function roundTripNodeRefField(card: string, nodeLabel: string, prefix: string, label: string) {
  test(`${card}: "${label}" node-reference picker round-trips`, async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlowWithTargets(page, card, nodeLabel, prefix);
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode(nodeLabel);
      await sidebar.fillField(label, 'Call Tool');
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await page.locator('.react-flow__node').nth(1).click();
      await expect.soft(sidebar.readField(label)).resolves.toBe('Call Tool');
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
}

test.describe('condition — per-field round-trip', () => {
  roundTripField('Condition (If/Else)', 'Condition', 'rt-cond', 'Expression', 'context["status"] == "approved"');
  roundTripNodeRefField('Condition (If/Else)', 'Condition', 'rt-cond', 'True Branch');
  roundTripNodeRefField('Condition (If/Else)', 'Condition', 'rt-cond', 'False Branch');

  test('True Branch / False Branch pickers list real canvas nodes and exclude the node itself', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlowWithTargets(page, 'Condition (If/Else)', 'Condition', 'rt-cond-opts');
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode('Condition');

      const trigger = page.locator('#true-node');
      await trigger.click();
      const optionTexts = await page.getByRole('option').allInnerTexts();
      expect(optionTexts).toContain('Call Tool');
      expect(optionTexts).toContain('Transform Data');
      // The Condition node itself must not be offered as its own target.
      expect(optionTexts).not.toContain('Condition');
      await page.keyboard.press('Escape');
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  test('a saved True Branch reference to a since-deleted node is preserved as a "Missing node" option, not dropped', async ({
    page,
    baseURL,
  }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlowWithTargets(page, 'Condition (If/Else)', 'Condition', 'rt-cond-del');
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode('Condition');
      await sidebar.fillField('True Branch', 'Call Tool');
      await sidebar.fillField('False Branch', 'Transform Data');
      await canvas.settle();
      await canvas.save();

      await canvas.deleteNode('Call Tool');
      await canvas.selectNode('Condition');
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await canvas.selectNode('Condition');

      const trueBranchAfterDelete = await sidebar.readField('True Branch');
      expect(trueBranchAfterDelete).toMatch(/^Missing node: .+\(not found\)$/);
      // Untouched reference must be unaffected by the deletion of the other one.
      await expect.soft(sidebar.readField('False Branch')).resolves.toBe('Transform Data');
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
});

test.describe('loop — per-field round-trip', () => {
  roundTripField('Loop', 'Loop', 'rt-loop', 'Iterate Over (Context Key)', 'items');
  roundTripField('Loop', 'Loop', 'rt-loop', 'Item Variable', 'current_item');
  roundTripField('Loop', 'Loop', 'rt-loop', 'Index Variable', 'current_index');
  roundTripField('Loop', 'Loop', 'rt-loop', 'Max Iterations', '25');
  roundTripNodeRefField('Loop', 'Loop', 'rt-loop', 'Loop Body Node');
  roundTripNodeRefField('Loop', 'Loop', 'rt-loop', 'Done Node');

  test('Loop Body Node / Done Node pickers list real canvas nodes and exclude the node itself', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlowWithTargets(page, 'Loop', 'Loop', 'rt-loop-opts');
      flowId = built.flowId;
      const { canvas } = built;
      await canvas.selectNode('Loop');

      const trigger = page.locator('#loop-body');
      await trigger.click();
      const optionTexts = await page.getByRole('option').allInnerTexts();
      expect(optionTexts).toContain('Call Tool');
      expect(optionTexts).toContain('Transform Data');
      expect(optionTexts).not.toContain('Loop');
      await page.keyboard.press('Escape');
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  test('a saved Loop Body Node reference to a since-deleted node is preserved as a "Missing node" option, not dropped', async ({
    page,
    baseURL,
  }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlowWithTargets(page, 'Loop', 'Loop', 'rt-loop-del');
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode('Loop');
      await sidebar.fillField('Loop Body Node', 'Call Tool');
      await sidebar.fillField('Done Node', 'Transform Data');
      await canvas.settle();
      await canvas.save();

      await canvas.deleteNode('Call Tool');
      await canvas.selectNode('Loop');
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await canvas.selectNode('Loop');

      const loopBodyAfterDelete = await sidebar.readField('Loop Body Node');
      expect(loopBodyAfterDelete).toMatch(/^Missing node: .+\(not found\)$/);
      await expect.soft(sidebar.readField('Done Node')).resolves.toBe('Transform Data');
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
});

test.describe('http-request — per-field round-trip', () => {
  roundTripField('HTTP Request', 'HTTP Request', 'rt-http', 'URL', 'https://api.example.com/endpoint');
  roundTripField('HTTP Request', 'HTTP Request', 'rt-http', 'Method', 'POST');
  roundTripField('HTTP Request', 'HTTP Request', 'rt-http', 'Timeout (seconds)', '45');
  roundTripField('HTTP Request', 'HTTP Request', 'rt-http', 'Save Result To Context', 'api_response');

  test('HTTP Request: "Headers (JSON)" round-trips valid JSON as an object', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlow(page, 'HTTP Request', 'rt-http-hdr');
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode('HTTP Request');
      await sidebar.fillField('Headers (JSON)', '{\n  "Authorization": "Bearer {{token}}"\n}');
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await page.locator('.react-flow__node').nth(1).click();
      const headers = await sidebar.readField('Headers (JSON)');
      expect(JSON.parse(headers)).toEqual({ Authorization: 'Bearer {{token}}' });
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  test('HTTP Request: "Body" round-trips valid JSON as an object', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlow(page, 'HTTP Request', 'rt-http-body');
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode('HTTP Request');
      await sidebar.fillField('Body', '{\n  "key": "{{context.value}}"\n}');
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await page.locator('.react-flow__node').nth(1).click();
      const body = await sidebar.readField('Body');
      expect(JSON.parse(body)).toEqual({ key: '{{context.value}}' });
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  // DEFECT (documented, not fixed): RightSidebar.tsx's onChange handlers for
  // both Headers and Body do `try { JSON.parse(...) } catch { save the raw
  // string instead }`. There is no visible error state — invalid JSON is
  // silently accepted as a plain string. This round-trips "successfully" in
  // the sense that the string comes back unchanged, but it means a user who
  // makes a typo (e.g. a trailing comma, or forgetting a closing brace) gets
  // no feedback that their headers/body will NOT be sent as parsed JSON at
  // flow-run time — the flow engine likely expects an object and will either
  // choke on or misinterpret the raw string. Naming this test to document
  // the defect per the task's instruction not to weaken assertions to hide it.
  test('DEFECT: HTTP Request "Headers (JSON)" silently accepts invalid JSON as a plain string with no error shown', async ({
    page,
    baseURL,
  }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlow(page, 'HTTP Request', 'rt-http-hdr-bad');
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode('HTTP Request');
      const invalidJson = '{ "Authorization": "Bearer abc", }'; // trailing comma — invalid JSON
      await sidebar.fillField('Headers (JSON)', invalidJson);
      await canvas.settle();
      // No error/warning surfaced anywhere in the sidebar for invalid JSON.
      await expect(page.getByText(/invalid json/i)).toHaveCount(0);
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await page.locator('.react-flow__node').nth(1).click();
      const got = await sidebar.readField('Headers (JSON)');
      // The raw invalid string survives byte-for-byte — it was stored as a
      // string, not silently dropped or coerced to {} — but it is NOT valid
      // JSON, so downstream consumers expecting an object will misbehave.
      expect(got).toBe(invalidJson);
      expect(() => JSON.parse(got)).toThrow();
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  test('DEFECT: HTTP Request "Body" silently accepts invalid JSON as a plain string with no error shown', async ({
    page,
    baseURL,
  }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlow(page, 'HTTP Request', 'rt-http-body-bad');
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode('HTTP Request');
      const invalidJson = '{ "key": "value" '; // missing closing brace — invalid JSON
      await sidebar.fillField('Body', invalidJson);
      await canvas.settle();
      await expect(page.getByText(/invalid json/i)).toHaveCount(0);
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await page.locator('.react-flow__node').nth(1).click();
      const got = await sidebar.readField('Body');
      expect(got).toBe(invalidJson);
      expect(() => JSON.parse(got)).toThrow();
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
});
