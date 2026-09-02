import { test, expect } from '@playwright/test';
import { newApiContext, uniqueFlowName } from './flowApi';

/**
 * A failed flow run must show WHY it failed. The engine populates
 * Flow Run.last_error (e.g. "Node 'x' not found in definition") and the
 * frontend already fetches it, but no flow component rendered it: users saw
 * only a red "Failed" badge and had to guess from raw context JSON.
 */
test('a failed run shows its error text in the run viewer', async ({ page, baseURL }) => {
  const origin = new URL(baseURL!).origin;
  const api = await newApiContext(origin);
  const flowId = uniqueFlowName('err').replace(/[^a-zA-Z0-9-]/g, '-');

  // Build a flow that fails deterministically: a condition pointing at a node
  // that does not exist. No credentials or providers needed.
  // Must FAIL AT RUNTIME while still PASSING save-time validation - those are
  // now different things. A dangling condition target (the obvious choice) is
  // rejected on activation by Flow Definition.validate(), so the flow could
  // never be activated to run at all. A tool.call naming a tool that does not
  // exist satisfies validation (the required `tool_name` key IS present) and
  // fails in _exec_tool_call when the registry lookup misses.
  const definition = {
    schema_version: 1, id: flowId, version: 1, entry: 'trig',
    nodes: [
      { id: 'trig', type: 'trigger.webhook', config: {} },
      { id: 'n1', type: 'tool.call', config: { tool_name: 'ghost_tool_does_not_exist', args: {} } },
    ],
    edges: [{ from: 'trig', to: 'n1', type: 'always' }],
    settings: { mode: 'normal', max_hops: 10 }, metadata: { name: flowId },
  };
  let created = await api.post('/api/resource/Flow Definition', {
    data: { flow_id: flowId, flow_name: flowId, status: 'Active', definition_json: JSON.stringify(definition) },
  });
  expect(created.ok(), `create failed: ${await created.text()}`).toBeTruthy();

  const run = await api.post('/api/method/huf.ai.flow_api.run_flow', { data: { flow_id: flowId } });
  expect(run.ok(), `run failed: ${await run.text()}`).toBeTruthy();
  const runId = (await run.json()).message.flow_run_id;

  // Ground truth: the document really did record the error.
  const detail = await api.get(`/api/resource/Flow Run/${runId}`);
  const doc = (await detail.json()).data;
  expect(doc.status).toBe('Failed');
  expect(doc.last_error).toContain('ghost_tool_does_not_exist');

  // The UI must show that same error, not just a red badge.
  await page.goto(`flows/${flowId}`);
  await page.waitForLoadState('networkidle').catch(() => {});
  // The run list opens from the header's "Runs" button (History icon), not
  // from anything labelled "Run History" - that string is the panel heading.
  await page.getByRole('button', { name: /^runs$/i }).click();
  await page.getByText(runId, { exact: false }).first().click();
  const errorBlock = page.getByTestId('flow-run-error');
  await expect(errorBlock).toBeVisible({ timeout: 15000 });
  await expect(errorBlock).toContainText('ghost_tool_does_not_exist');

  await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
  await api.dispose();
});
