import { test, expect } from '@playwright/test';
import { FlowsListPage } from './FlowsListPage';
import { FlowCanvasPage } from './FlowCanvasPage';
import { NodeModal } from './NodeModal';
import { ConfigSidebar } from './ConfigSidebar';
import { newApiContext, uniqueFlowName } from './flowApi';

/**
 * Verifies the ENGINE-BACKED trigger controls added to RightSidebar.tsx
 * ("Runs on a schedule (engine)" / "Fires on a document event (engine)")
 * actually create/update/delete a real Agent Trigger record via
 * huf/ai/flow_api.py's set_flow_schedule / set_flow_doc_event_trigger /
 * get_flow_trigger / clear_flow_trigger — unlike the legacy
 * intervalType/interval/cronExpression and doctype/event node-config
 * fields (covered separately, and asserted as engine-inert, by
 * fields-triggers.spec.ts), which this suite deliberately leaves alone.
 *
 * Assertions go through get_flow_trigger directly (a backend call, not a
 * UI reflection) so a UI-only illusion of persistence can't pass.
 */

async function getTriggersForFlow(api: Awaited<ReturnType<typeof newApiContext>>, flowId: string) {
  const res = await api.get('/api/method/huf.ai.flow_api.get_flow_trigger', {
    params: { flow_id: flowId },
  });
  if (!res.ok()) throw new Error(`get_flow_trigger(${flowId}) failed: ${res.status()} ${await res.text()}`);
  const json = await res.json();
  return json.message as Array<Record<string, unknown>>;
}

/** Close any open Radix dialog so its overlay stops intercepting sidebar clicks. */
async function dismissAnyOpenDialog(page: import('@playwright/test').Page) {
  const dialog = page.getByRole('dialog');
  for (let i = 0; i < 3; i++) {
    if (!(await dialog.count())) return;
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
  }
  await expect(dialog).toHaveCount(0, { timeout: 5000 });
}

test.describe('flow trigger engine wiring (Schedule / Doc Event)', () => {
  test('configuring a Schedule trigger on canvas creates a real Agent Trigger', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const list = new FlowsListPage(page);
      const canvas = new FlowCanvasPage(page);
      const modal = new NodeModal(page);
      const sidebar = new ConfigSidebar(page);

      flowId = await list.createFlow(uniqueFlowName('e2e-trig-sched'));
      await canvas.addTrigger();
      await modal.waitForOpen('trigger');
      await modal.selectCard('Schedule');
      await modal.saveTriggerConfiguration();
      await canvas.settle();
      await canvas.save();
      // Reload before re-selecting: the trigger-creation modal's Radix
      // overlay otherwise stays mounted over the sidebar and swallows
      // clicks. This mirrors fields-triggers.spec.ts's proven sequence.
      await canvas.reload();
      await canvas.settle();

      // Re-select the entry node on canvas so RightSidebar's hydration
      // effect (getFlowTrigger) runs and the engine control renders.
      // Clicking the entry trigger node also re-opens the "Select Trigger"
      // modal, whose Radix overlay covers (and swallows clicks meant for)
      // the sidebar behind it — dismiss it before touching any control.
      await page.locator('.react-flow__node').nth(0).click();
      await dismissAnyOpenDialog(page);

      await sidebar.fillField('Frequency', 'Daily');
      // Wait for the save round-trip (setFlowSchedule) to resolve and the
      // "Every N intervals" control to appear, proving hydration reflected
      // the created trigger back into the UI.
      await expect(page.locator('#engine-interval-count')).toBeVisible({ timeout: 15000 });

      const triggers = await getTriggersForFlow(api, flowId);
      const schedule = triggers.find((t) => t.trigger_type === 'Schedule');
      expect(schedule, 'expected a Schedule Agent Trigger to exist for this flow').toBeTruthy();
      expect(schedule!.scheduled_interval).toBe('Daily');
      expect(schedule!.flow_id).toBe(flowId);

      // Change the interval count and confirm it updates the SAME record
      // (idempotent via trigger_name) rather than creating a second one.
      await sidebar.fillField('Every N intervals', '3');
      // The field persists on blur (writing per keystroke would fire one API
      // call per character, and those can land out of order), so commit it.
      await page.locator('#engine-interval-count').blur();
      await expect
        .poll(async () => {
          const rows = await getTriggersForFlow(api, flowId!);
          return rows.filter((t) => t.trigger_type === 'Schedule').length;
        }, { timeout: 15000 })
        .toBe(1);
      // The write is async, so poll for the persisted value rather than reading
      // once straight after blur.
      await expect
        .poll(async () => {
          const rows = await getTriggersForFlow(api, flowId!);
          return rows.find((t) => t.trigger_type === 'Schedule')?.interval_count;
        }, { timeout: 15000, intervals: [250, 500, 1000] })
        .toBe(3);
      const updated = (await getTriggersForFlow(api, flowId)).find((t) => t.trigger_type === 'Schedule');
      // Still the SAME trigger record - editing must update, never orphan a
      // second schedule for the same flow.
      expect(updated!.trigger_name).toBe(schedule!.trigger_name);

      // Remove the schedule and confirm the Agent Trigger record is gone.
      await page.getByRole('button', { name: 'Remove schedule' }).click();
      await expect
        .poll(async () => {
          const rows = await getTriggersForFlow(api, flowId!);
          return rows.filter((t) => t.trigger_type === 'Schedule').length;
        }, { timeout: 15000 })
        .toBe(0);
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  test('configuring a Doc Event trigger on canvas creates a real Agent Trigger', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const list = new FlowsListPage(page);
      const canvas = new FlowCanvasPage(page);
      const modal = new NodeModal(page);
      const sidebar = new ConfigSidebar(page);

      flowId = await list.createFlow(uniqueFlowName('e2e-trig-de'));
      await canvas.addTrigger();
      await modal.waitForOpen('trigger');
      await modal.selectCard('Data');
      await modal.saveTriggerConfiguration();
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();

      await page.locator('.react-flow__node').nth(0).click();
      await dismissAnyOpenDialog(page);

      // "ToDo" is a built-in Frappe DocType guaranteed to exist on every site.
      // Labels are suffixed "(Engine)" to disambiguate from the legacy
      // display-only "Document Type" / "Event Type" fields rendered above
      // them (see RightSidebar.tsx's doc-event branch).
      await sidebar.fillCombobox('Document Type (Engine)', 'ToDo');
      await sidebar.fillField('Event (Engine)', 'After Save');

      await expect
        .poll(async () => {
          const rows = await getTriggersForFlow(api, flowId!);
          return rows.filter((t) => t.trigger_type === 'Doc Event').length;
        }, { timeout: 15000 })
        .toBe(1);

      const triggers = await getTriggersForFlow(api, flowId);
      const docEvent = triggers.find((t) => t.trigger_type === 'Doc Event');
      expect(docEvent!.reference_doctype).toBe('ToDo');
      expect(docEvent!.doc_event).toBe('after_save');

      await page.getByRole('button', { name: 'Remove trigger' }).click();
      await expect
        .poll(async () => {
          const rows = await getTriggersForFlow(api, flowId!);
          return rows.filter((t) => t.trigger_type === 'Doc Event').length;
        }, { timeout: 15000 })
        .toBe(0);
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
});
