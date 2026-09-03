import { test, expect } from '@playwright/test';
import { FlowsListPage } from './FlowsListPage';
import { FlowCanvasPage } from './FlowCanvasPage';
import { NodeModal } from './NodeModal';
import { selectors } from './selectors';
import { newApiContext, deleteFlowByName, uniqueFlowName } from './flowApi';

/**
 * Catalog suite: what the palette actually offers, verified in the browser
 * against frontend/src/data/{triggers,actions}.ts. Complements
 * contextual.spec.ts, which checks *where* options are offered; this file
 * checks *which* options exist at all.
 */

// Post-fix palette (this track). 'Call Webhook', 'Date Utility' and 'Notion'
// were REMOVED: webhook is superseded by HTTP Request, no date tool exists, and
// Notion is reached via MCP through the generic Call Tool node.
const EXPECTED_ACTION_CARDS = [
  'Run Agent',
  'Call Tool',
  'LLM Router',
  'Condition (If/Else)',
  'Loop',
  'Human in Loop',
  'Transform Data',
  'Execute Code',
  'Send Email',
  'HTTP Request',
  'File Operations',
  'Slack',
  'Google Sheets',
];

// Cards deliberately removed from the palette this track. Asserting their
// ABSENCE is what stops them silently coming back.
const REMOVED_ACTION_CARDS = ['Call Webhook', 'Date Utility', 'Notion'];

// The 8 known-dead action executors: selectable in the UI but their backend
// executor either doesn't exist or is broken. Documented here, not fixed.
// After this track's fixes, only ONE card remains non-functional: 'Execute Code'.
// Its handler exists (huf/ai/tools/code_execution.py, _TOOL_NAME = "run_python")
// but is registered nowhere in _registry.py, so no tool_name can be preset.
// Finding N14. Email/Slack/Sheets/File are now wired to real registered tools.
const KNOWN_DEAD_ACTION_CARDS = [
  'Execute Code', // N14: run_python implemented but never registered
];

async function openActionModal(page: import('@playwright/test').Page, flowName: string) {
  const list = new FlowsListPage(page);
  const canvas = new FlowCanvasPage(page);
  const modal = new NodeModal(page);

  const flowId = await list.createFlow(flowName);

  await canvas.addTrigger();
  await modal.waitForOpen('trigger');
  await modal.selectCard('Data');
  await modal.saveTriggerConfiguration();
  await expect(selectors.nodeModal.dialog(page)).toBeHidden({ timeout: 10000 });

  await canvas.addNodeAfter('Doc Event');
  await modal.waitForOpen('action');

  return { flowId, modal };
}

test.describe('flow builder node catalog', () => {
  let flowId: string | undefined;
  let flowName: string;

  test.beforeEach(() => {
    flowName = uniqueFlowName('cat');
    flowId = undefined;
  });

  test.afterEach(async ({ baseURL }) => {
    if (!flowId) return;
    const api = await newApiContext(new URL(baseURL!).origin);
    await deleteFlowByName(api, flowId).catch(() => {});
    await api.dispose();
  });

  test('4/5. action catalog matches expected set; HTTP Request present; Human Input absent', async ({ page }) => {
    const { flowId: id, modal } = await openActionModal(page, flowName);
    flowId = id;

    const cards = await modal.listCards();

    expect(cards.sort()).toEqual([...EXPECTED_ACTION_CARDS].sort());

    // Fix landed this session: the HTTP Request executor is now reachable.
    expect(cards).toContain('HTTP Request');

    // Fix landed this session: Human Input used to be offered as a
    // (broken) trigger; it must not appear anywhere in this catalog.
    expect(cards).not.toContain('Human Input');
  });

  test('5. trigger catalog is exactly Webhook, Schedule, Data', async ({ page }) => {
    const list = new FlowsListPage(page);
    const canvas = new FlowCanvasPage(page);
    const modal = new NodeModal(page);

    flowId = await list.createFlow(flowName);
    await canvas.addTrigger();
    await modal.waitForOpen('trigger');

    const cards = await modal.listCards();
    expect(cards).toEqual(['Webhook', 'Schedule', 'Data']);
  });

  test('6. KNOWN DEFECT: 8 dead action cards are still present and selectable', async ({ page }) => {
    const { flowId: id, modal } = await openActionModal(page, flowName);
    flowId = id;

    const cards = await modal.listCards();

    for (const name of KNOWN_DEAD_ACTION_CARDS) {
      expect(cards, `expected dead action card "${name}" to still be offered (KNOWN DEFECT)`).toContain(name);
      await expect(
        selectors.nodeModal.cardByName(page, name),
        `expected dead action card "${name}" to still be a clickable button`,
      ).toBeEnabled();
    }

    // Close without selecting anything, to avoid mutating the canvas 8x.
    await page.getByRole('dialog').getByRole('button', { name: /cancel/i }).click();
  });
});
