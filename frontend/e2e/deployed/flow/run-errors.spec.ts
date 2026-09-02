import { test, expect } from '@playwright/test';
import { FlowsListPage } from './FlowsListPage';
import { FlowCanvasPage } from './FlowCanvasPage';
import {
  newApiContext,
  deleteFlowByName,
  getFlowRun,
  getFlowDefinition,
  saveFlowDefinition,
  runFlowApi,
  uniqueFlowName,
} from './flowApi';

/**
 * Is a run failure legible to the user? We build a flow that DEFINITELY
 * fails at runtime (a condition node whose true_node names a nonexistent
 * node id — engine-rejected at huf/ai/flow_engine.py:276-279 with
 * "Node 'X' not found in definition"), run it, and check every place the
 * error could plausibly surface: the run history sheet, the run detail
 * sheet (FlowRunViewer.tsx), and any toast.
 *
 * ROUTE USED: the node-id <Select> in RightSidebar.tsx only ever offers
 * ids of nodes that currently exist in the flow (renderNodeIdSelect) — it
 * cannot be typed into, so the UI itself cannot express "true_node points
 * at a node id that never existed". We build this flow via the REST API
 * (flowApi.ts saveFlowDefinition, the same whitelisted method the frontend
 * calls) and then open it in the UI for the run/inspect steps, which a
 * user could equally reach by having a node deleted out from under them
 * (see negative.spec.ts test 3) or via any out-of-band definition edit.
 */
test.describe.serial('run failure legibility (run-errors)', () => {
  let api: Awaited<ReturnType<typeof newApiContext>>;
  const flowIdsToClean: string[] = [];

  test.beforeAll(async ({ baseURL }) => {
    const origin = new URL(baseURL!).origin;
    api = await newApiContext(origin);
  });

  test.afterAll(async () => {
    for (const id of flowIdsToClean) {
      await deleteFlowByName(api, id).catch(() => {});
    }
    await api.dispose();
  });

  test('a run that fails with a real engine error is NOT surfaced anywhere in the UI (KNOWN DEFECT)', async ({ page }) => {
    const flowName = uniqueFlowName('run-err');
    const list = new FlowsListPage(page);
    const canvas = new FlowCanvasPage(page);

    // 1. Create the flow through the UI so it has a real flow_id and is
    //    reachable at /flows/:id the normal way.
    await list.goto();
    const flowId = await list.createFlow(flowName);
    flowIdsToClean.push(flowId);

    // 2. Overwrite its definition via the API: entry node is a condition
    //    whose true_node/false_node reference a node id that does not
    //    exist anywhere in `nodes`. This is exactly the "dangling
    //    reference" shape from negative.spec.ts test 3, just constructed
    //    directly since the UI can't type a never-existed id.
    const brokenDefinition = {
      schema_version: 1,
      id: flowId,
      version: 1,
      entry: 'cond-1',
      nodes: [
        {
          id: 'cond-1',
          type: 'condition',
          config: { expression: 'true', true_node: 'does-not-exist', false_node: null },
          _position: { x: 250, y: 100 },
          _label: 'Condition (If/Else)',
        },
      ],
      edges: [],
      settings: { mode: 'normal', max_hops: 100 },
      metadata: { name: flowName, category: 'Uncategorized' },
    };
    await saveFlowDefinition(api, flowId, brokenDefinition);

    // Sanity: confirm the broken definition really did save as broken
    // (flow_definition.py's validate() checks the `edges` array's from/to,
    // not a condition node's true_node/false_node config — so this saves
    // cleanly with no server-side rejection).
    const savedDefn = await getFlowDefinition(api, flowId);
    expect(savedDefn.definition_json.nodes[0].config?.true_node).toBe('does-not-exist');

    // 3. Run it via the API (engine runs synchronously — see
    //    huf/ai/flow_api.py run_flow(): "Run synchronously for now").
    const runResult = await runFlowApi(api, flowId);
    expect(runResult.status).toBe('Failed');

    const runDetail = await getFlowRun(api, runResult.flow_run_id);
    expect(runDetail.status).toBe('Failed');
    // This is the ground truth: the engine recorded the exact reason.
    expect(runDetail.last_error).toContain("not found in definition");
    expect(runDetail.last_error).toContain('does-not-exist');

    // 4. Now check the UI. Open the flow, open Run History, open the run
    //    detail sheet — everywhere last_error could be shown.
    await page.goto(`flows/${flowId}`);
    await canvas.settle();

    await page.getByRole('button', { name: /^runs$/i }).click();
    const runRow = page.locator('div', { hasText: runResult.flow_run_id }).last();
    await expect(runRow).toBeVisible({ timeout: 10000 });
    // The history row shows only a status badge ("Failed") and trigger
    // type/timestamp — confirm the raw error text is not printed here.
    await expect(page.getByText(runDetail.last_error!, { exact: false })).toHaveCount(0);
    await expect(page.getByText('Failed', { exact: true }).first()).toBeVisible();

    await runRow.click();

    // Run detail sheet (FlowRunViewer.tsx): shows Status/Current-Last-Node/
    // Hops/Context Variables. It never reads `run.last_error` anywhere in
    // its JSX (grepped: only the type declares the field, nothing renders
    // it) — confirm the exact error text the backend recorded is nowhere
    // on screen, anywhere in the sheet's rendered text.
    const sheet = page.locator('[role="dialog"], [data-state="open"]').last();
    await expect(page.getByText(/run details/i)).toBeVisible({ timeout: 10000 });
    const bodyText = await page.locator('body').innerText();
    expect(bodyText).not.toContain(runDetail.last_error!);
    expect(bodyText).not.toContain('not found in definition');

    // It does show the failed status badge and current_node_id, so the
    // user isn't left with literally nothing — just nothing that explains
    // WHY it failed.
    await expect(page.getByText('Failed', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('cond-1', { exact: false })).toBeVisible();

    void sheet;

    // MAJOR USABILITY DEFECT, asserted explicitly: `last_error` is
    // populated in the Flow Run document (confirmed above via the API)
    // but is rendered NOWHERE in the UI — not the run history list, not
    // the run detail sheet, not a toast. A user whose flow fails has no
    // way to learn why without querying the API/DB directly.

    // FAIL-CHECK PERFORMED: temporarily changed the last assertion to
    // `expect(bodyText).toContain(runDetail.last_error!)`; it failed as
    // expected (the text truly is absent from the page), confirming this
    // is a real, load-bearing assertion and not a vacuous one. Reverted
    // to the `.not.toContain` form above, which is the correct/documented
    // finding.
  });

  test('KNOWN DEFECT: the "Run" button reports success even when the flow run itself failed', async ({ page }) => {
    const flowName = uniqueFlowName('run-err-toast');
    const list = new FlowsListPage(page);
    const canvas = new FlowCanvasPage(page);

    await list.goto();
    const flowId = await list.createFlow(flowName);
    flowIdsToClean.push(flowId);

    const brokenDefinition = {
      schema_version: 1,
      id: flowId,
      version: 1,
      entry: 'cond-1',
      nodes: [
        {
          id: 'cond-1',
          type: 'condition',
          config: { expression: 'true', true_node: 'still-does-not-exist', false_node: null },
          _position: { x: 250, y: 100 },
          _label: 'Condition (If/Else)',
        },
      ],
      edges: [],
      settings: { mode: 'normal', max_hops: 100 },
      metadata: { name: flowName, category: 'Uncategorized' },
    };
    await saveFlowDefinition(api, flowId, brokenDefinition);

    await page.goto(`flows/${flowId}`);
    await canvas.settle();

    // FlowsHeaderActions.tsx handleRun(): calls runFlow() (which awaits the
    // synchronous engine run and returns {flow_run_id, status, ...}) then
    // unconditionally does toast.success('Flow run started', ...) — it
    // never inspects result.status. Confirm this toast appears even though
    // the run itself will have status: Failed.
    await canvas.run();
    await expect(page.getByText(/flow run started/i)).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/failed to run flow/i)).toHaveCount(0);

    // Ground truth: the run this success toast was celebrating actually failed.
    const runs = await api.get('/api/method/huf.ai.flow_api.list_flow_runs', {
      params: { flow_id: flowId },
    });
    const runsJson = await runs.json();
    const latestRun = runsJson.message?.[0];
    expect(latestRun).toBeTruthy();
    const runDetail = await getFlowRun(api, latestRun.name);
    expect(runDetail.status).toBe('Failed');

    // KNOWN DEFECT: the toast the user actually sees after clicking Run
    // ("Flow run started") gives no indication the run failed — it looks
    // identical to a successful run's toast. The only way to learn the run
    // failed is to separately open Run History.
  });
});
