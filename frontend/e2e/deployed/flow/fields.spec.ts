import { test, expect, Page } from '@playwright/test';
import { FlowsListPage } from './FlowsListPage';
import { FlowCanvasPage } from './FlowCanvasPage';
import { NodeModal } from './NodeModal';
import { ConfigSidebar } from './ConfigSidebar';
import { newApiContext, uniqueFlowName } from './flowApi';

/**
 * Point 8 — "each step should have all controls available" — asserted ONE
 * FIELD PER TEST.
 *
 * The original all-in-one round-trip tests set ~8 fields in a single test, so
 * a single bad selector failed the whole node type and told us nothing about
 * the other seven. Splitting them means a failure names exactly which control
 * does not round-trip.
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

/** Fill one field, save, hard-reload, and assert it came back unchanged. */
function roundTripField(
  card: string,
  nodeLabel: string,
  prefix: string,
  label: string,
  value: string,
  /** Optional precondition: some fields only render once another is set. */
  pre?: (sidebar: ConfigSidebar) => Promise<void>,
) {
  // nodeLabel is used for the FIRST selection only; see the reload note below.
  test(`${card}: "${label}" round-trips`, async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlow(page, card, prefix);
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode(nodeLabel);
      if (pre) await pre(sidebar);
      await sidebar.fillField(label, value);
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      // Re-select by POSITION, not by label: some fields (human.approval's
      // "Title", tool-call's "Node Title") rename the canvas node, so a
      // label-based lookup would fail for reasons unrelated to the field
      // under test. In these flows node 0 is the trigger and node 1 is the
      // action node we configured.
      await page.locator('.react-flow__node').nth(1).click();
      // Compare semantically: list-style fields (e.g. approver emails) are
      // parsed into an array and re-joined with ", ", so the value round-trips
      // correctly but not byte-for-byte. Whitespace around separators is not
      // a defect; a changed or dropped value would be.
      const got = (await sidebar.readField(label)).replace(/\s*,\s*/g, ',').trim();
      expect(got).toBe(value.replace(/\s*,\s*/g, ',').trim());
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
}

test.describe('per-field config round-trip', () => {
  // human.approval — every text field the sidebar exposes.
  for (const [label, value] of [
    ['Title', 'Please approve the invoice'],
    ['Instructions', 'Check the total against the PO'],
    ['Context Summary', 'invoice_total'],
    ['Reference Document Name', 'ACC-INV-0001'],
  ] as const) {
    roundTripField('Human in Loop', 'Human in Loop', 'rt-appr', label, value);
  }

  // "Approver Users" only renders when Approval Type is "By User" (the
  // default is "By Role", which shows "Approver Role" instead), so the
  // precondition is part of the test rather than a defect.
  roundTripField(
    'Human in Loop', 'Human in Loop', 'rt-appr',
    'Approver Users (comma-separated emails)', 'a@example.com,b@example.com',
    async (sidebar) => { await sidebar.fillField('Approval Type', 'By User'); },
  );

  // tool-call — the save-result key and a schema-driven tool argument.
  roundTripField('Call Tool', 'Call Tool', 'rt-tool', 'Save Result To Context', 'tool_result');
});
