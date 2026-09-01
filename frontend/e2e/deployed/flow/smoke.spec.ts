import { test, expect } from '@playwright/test';
import { FlowsListPage } from './FlowsListPage';
import { newApiContext, deleteFlowByName, flowExists, uniqueFlowName } from './flowApi';

/**
 * Proves the harness works end to end against the live bench: create a
 * uniquely-named flow through the real UI, confirm it shows up in the
 * flows list, delete it through the real UI, and confirm it's gone —
 * both in the UI and via a direct API check.
 */
test.describe('flow builder smoke', () => {
  test('create, see, delete a flow', async ({ page, baseURL }) => {
    const flowName = uniqueFlowName('smoke');
    const list = new FlowsListPage(page);
    const origin = new URL(baseURL!).origin;
    const api = await newApiContext(origin);

    let flowId: string | undefined;
    try {
      await list.goto();
      flowId = await list.createFlow(flowName);
      expect(flowId).toBeTruthy();

      await list.goto();
      await list.assertVisible(flowName);

      await list.deleteFlow(flowName);
      await list.assertGone(flowName);

      if (flowId) {
        expect(await flowExists(api, flowId)).toBe(false);
      }
    } finally {
      // Best-effort cleanup in case an assertion failed mid-test.
      if (flowId) {
        await deleteFlowByName(api, flowId).catch(() => {});
      }
      await api.dispose();
    }
  });
});
