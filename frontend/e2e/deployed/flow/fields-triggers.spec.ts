import { test, expect, Page } from '@playwright/test';
import { FlowsListPage } from './FlowsListPage';
import { FlowCanvasPage } from './FlowCanvasPage';
import { NodeModal } from './NodeModal';
import { ConfigSidebar } from './ConfigSidebar';
import { newApiContext, uniqueFlowName, getFlowDefinition } from './flowApi';

/**
 * Point 8 — exhaustive per-field round-trip coverage for the THREE TRIGGER
 * types (webhook, schedule, doc-event), mirroring fields.spec.ts's
 * one-field-per-test approach for action nodes.
 *
 * Field inventory, read from RightSidebar.tsx (renderTriggerForm):
 *
 * webhook (config.type === 'webhook', ~line 205):
 *   - "Webhook URL (Auto-generated)" — readOnly, derived from flow id + auth. Not user-editable, not tested here.
 *   - "Authentication Key (Optional)" -> config.auth
 *   - "HTTP Method (Expected)" -> config.method (Select: GET/POST/PUT/DELETE)
 *
 * schedule (config.type === 'schedule', ~line 260):
 *   - "Schedule Type" -> config.intervalType (Select: minutes/hours/days/custom)
 *   - "Interval" -> config.interval (number input, rendered only when intervalType !== 'custom')
 *   - "Cron Expression" -> config.cronExpression (rendered only when intervalType === 'custom')
 *
 * doc-event (config.type === 'doc-event', ~line 307):
 *   - "Document Type" -> config.doctype (Combobox, options loaded from getDocTypes())
 *   - "Event Type" -> config.event (Select: save/update/delete/before-save/before-update/before-delete)
 *
 * ENGINE-FACING TRUTH (huf/ai/flow_engine.py _execute_node dispatch):
 *   - trigger.webhook -> _exec_trigger_webhook reads NOTHING from config; it's a
 *     pure passthrough of the already-loaded run context. `auth` is validated
 *     separately, before the flow even runs, by _webhook_key_is_valid /
 *     _resolve_flow_by_webhook_key in huf/ai/flow_api.py, which read
 *     node_config.get("auth") or node_config.get("apiKey") (alias). `method`
 *     is never read by any executor for a trigger.webhook node — the http
 *     request's own `method` config field belongs to a different node type
 *     (http_request), not the trigger.
 *   - trigger.schedule -> _exec_trigger_schedule reads config.get("cron") and
 *     config.get("schedule_name"). The UI writes intervalType / interval /
 *     cronExpression — NO KEY OVERLAP with what the engine reads at all, so a
 *     schedule configured through the UI can never actually produce a
 *     "cron" value the engine looks for. This is a real defect, asserted
 *     below rather than hidden.
 *   - trigger.doc-event -> _exec_trigger_doc_event reads ctx (not config)
 *     directly, but the config_schema advertised by get_node_types
 *     (huf/ai/flow_api.py) and the doc-event dispatch matching elsewhere both
 *     key off config.doctype / config.event, which IS what the UI writes —
 *     this trigger's fields genuinely round-trip end to end.
 */

async function buildTriggerFlow(page: Page, prefix: string) {
  const list = new FlowsListPage(page);
  const canvas = new FlowCanvasPage(page);
  const modal = new NodeModal(page);
  const flowId = await list.createFlow(uniqueFlowName(prefix));
  await canvas.addTrigger();
  await modal.waitForOpen('trigger');
  return { canvas, modal, flowId, sidebar: new ConfigSidebar(page) };
}

/**
 * Fill one trigger field, save, hard-reload, and assert it survives via the UI.
 *
 * `label` is used to FILL the field while the NodeSelectionModal's own config
 * form is still open. `readLabel` (defaults to `label`) is used to read the
 * field back afterwards, from RightSidebar's renderTriggerForm on the
 * re-selected canvas node. For schedule/doc-event these are the same string
 * -- both components share identical label text. For webhook they diverge:
 * the modal labels its fields "HTTP Method" / "Security — API Key
 * (Optional)" while RightSidebar (post-save, on canvas selection) labels the
 * exact same config keys "HTTP Method (Expected)" / "Authentication Key
 * (Optional)" -- two components, two copies of the label text, out of sync
 * with each other. Not a defect in the underlying config (both write/read
 * `config.method` / `config.auth`), just inconsistent UI copy, so the test
 * accounts for it rather than asserting a false failure.
 */
function roundTripTriggerField(
  triggerCard: 'Webhook' | 'Schedule' | 'Data',
  prefix: string,
  label: string,
  value: string,
  /** Optional precondition after the trigger card is selected but before saving/filling, e.g. to switch Schedule Type so a conditional field renders. */
  pre?: (sidebar: ConfigSidebar) => Promise<void>,
  readLabel: string = label,
) {
  test(`${triggerCard} trigger: "${label}" round-trips`, async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildTriggerFlow(page, prefix);
      flowId = built.flowId;
      const { canvas, modal, sidebar } = built;
      await modal.selectCard(triggerCard);
      if (pre) await pre(sidebar);
      await sidebar.fillField(label, value);
      await modal.saveTriggerConfiguration();
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      // Re-select by POSITION: the entry node is always node 0, and its
      // canvas label changes with the configured trigger type ("Webhook" /
      // "Schedule Trigger" / "Doc Event"), so a label-based lookup would be
      // fragile in a way unrelated to the field under test.
      await page.locator('.react-flow__node').nth(0).click();
      const got = (await sidebar.readField(readLabel)).replace(/\s*,\s*/g, ',').trim();
      expect(got).toBe(value.replace(/\s*,\s*/g, ',').trim());
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
}

test.describe('per-field trigger config round-trip (UI)', () => {
  // ---- webhook ----
  // KNOWN DEFECT, not a test-selector problem: NodeSelectionModal's webhook
  // config form writes the auth key into config.apiKey (TriggerConfig has a
  // separate `apiKey?: string` field), while RightSidebar's webhook form
  // (rendered once the node is selected on canvas) reads/writes a DIFFERENT
  // field, config.auth (see flow.types.ts lines 56-57: both `apiKey?` and
  // `auth?` exist on the same type). So a key entered at trigger-creation
  // time is invisible the moment you go back and select the node -- the
  // sidebar reads the wrong key. huf/ai/flow_api.py's webhook-auth check
  // reads `config.get("auth") or config.get("apiKey")` (both, as an alias)
  // so the backend tolerates this, but the frontend itself is inconsistent.
  // Asserted honestly below rather than hidden.
  test('KNOWN DEFECT: webhook auth key written by the modal (apiKey) is not read back by RightSidebar (auth)', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildTriggerFlow(page, 'rt-trig-wh');
      flowId = built.flowId;
      const { canvas, modal, sidebar } = built;
      await modal.selectCard('Webhook');
      await sidebar.fillField('Security — API Key (Optional)', 'wh-secret-abc123');
      await modal.saveTriggerConfiguration();
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await page.locator('.react-flow__node').nth(0).click();
      // RightSidebar's "Authentication Key (Optional)" reads config.auth,
      // which was never written -- it comes back empty, not the value just
      // entered through the creation modal.
      expect(await sidebar.readField('Authentication Key (Optional)')).toBe('');

      const def = await getFlowDefinition(api, flowId);
      const entry = def.definition_json.nodes.find((n) => n.id === def.definition_json.entry);
      const config = (entry?.config ?? {}) as Record<string, unknown>;
      expect(config.apiKey).toBe('wh-secret-abc123'); // what was actually persisted
      expect(config.auth).toBeUndefined(); // what RightSidebar / the "auth" key actually looks for
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
  roundTripTriggerField(
    'Webhook', 'rt-trig-wh', 'HTTP Method', 'PUT',
    undefined, 'HTTP Method (Expected)',
  );

  // ---- schedule ----
  roundTripTriggerField('Schedule', 'rt-trig-sch', 'Schedule Type', 'Hours');
  roundTripTriggerField(
    'Schedule', 'rt-trig-sch', 'Interval', '5',
    async (sidebar) => { await sidebar.fillField('Schedule Type', 'Minutes'); },
  );
  roundTripTriggerField(
    'Schedule', 'rt-trig-sch', 'Cron Expression', '0 */6 * * *',
    async (sidebar) => { await sidebar.fillField('Schedule Type', 'Custom (Cron)'); },
  );

  // ---- doc-event ----
  // "Document Type" is a Combobox loaded from getDocTypes(); "ToDo" is a
  // built-in Frappe DocType guaranteed to exist on every site, so no fixture
  // setup is required.
  test('Data trigger: "Document Type" round-trips', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildTriggerFlow(page, 'rt-trig-de');
      flowId = built.flowId;
      const { canvas, modal, sidebar } = built;
      await modal.selectCard('Data');
      await sidebar.fillCombobox('Document Type', 'ToDo');
      await modal.saveTriggerConfiguration();
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await page.locator('.react-flow__node').nth(0).click();
      const got = await sidebar.readCombobox('Document Type');
      expect(got).toContain('ToDo');
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  roundTripTriggerField('Data', 'rt-trig-de', 'Event Type', 'Update');
});

test.describe('trigger config: engine-facing persisted shape (API)', () => {
  test('webhook: method persists verbatim (engine never reads it); auth is written under a DIFFERENT key (apiKey) than RightSidebar reads (auth) — KNOWN DEFECT', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildTriggerFlow(page, 'rt-trig-wh-api');
      flowId = built.flowId;
      const { canvas, modal, sidebar } = built;
      await modal.selectCard('Webhook');
      // Fill via the modal's own label text ("Security — API Key
      // (Optional)" / "HTTP Method") -- these fields are being set while
      // NodeSelectionModal's config form is still open, before Save
      // Configuration; RightSidebar's post-save copy ("Authentication Key
      // (Optional)" / "HTTP Method (Expected)") doesn't exist yet here.
      await sidebar.fillField('Security — API Key (Optional)', 'engine-check-key-1');
      await sidebar.fillField('HTTP Method', 'DELETE');
      await modal.saveTriggerConfiguration();
      await canvas.settle();
      await canvas.save();

      const defn = await getFlowDefinition(api, flowId);
      const entry = defn.definition_json.nodes.find((n) => n.id === defn.definition_json.entry);
      expect(entry?.type).toBe('trigger.webhook');
      const config = (entry?.config ?? {}) as Record<string, unknown>;
      // `method` round-trips fine...
      expect(config.method).toBe('DELETE');
      // ...but _exec_trigger_webhook (huf/ai/flow_engine.py) reads NEITHER
      // `method` nor an auth key from config at all: it's a pure passthrough
      // of the already-loaded context, no config.get() call in it. `method`
      // is not consumed anywhere for this node type; it exists purely as UI
      // documentation of the expected HTTP verb.
      //
      // KNOWN DEFECT: the value entered through NodeSelectionModal's "Security
      // — API Key (Optional)" field is persisted as config.apiKey, NOT
      // config.auth (TriggerConfig — flow.types.ts lines 56-57 — carries both
      // `apiKey?` and `auth?` as separate fields for what is conceptually one
      // value). RightSidebar's own "Authentication Key (Optional)" field
      // reads/writes config.auth exclusively, so it never sees a key entered
      // at creation time. `_webhook_key_is_valid` in huf/ai/flow_api.py reads
      // `config.get("auth") or config.get("apiKey")` (both, as an alias), so
      // the backend auth check itself still works either way — this is a
      // frontend-only inconsistency between the two components, not an
      // engine-facing one.
      expect(config.apiKey).toBe('engine-check-key-1');
      expect(config.auth).toBeUndefined();
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  test('KNOWN DEFECT: schedule writes intervalType/interval, engine reads cron/schedule_name (no overlap)', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildTriggerFlow(page, 'rt-trig-sch-api');
      flowId = built.flowId;
      const { canvas, modal, sidebar } = built;
      await modal.selectCard('Schedule');
      await sidebar.fillField('Schedule Type', 'Hours');
      await sidebar.fillField('Interval', '3');
      await modal.saveTriggerConfiguration();
      await canvas.settle();
      await canvas.save();

      const defn = await getFlowDefinition(api, flowId);
      const entry = defn.definition_json.nodes.find((n) => n.id === defn.definition_json.entry);
      expect(entry?.type).toBe('trigger.schedule');
      const config = (entry?.config ?? {}) as Record<string, unknown>;
      // What the UI actually persists:
      expect(config.intervalType).toBe('hours');
      expect(config.interval).toBe(3);
      // What _exec_trigger_schedule (huf/ai/flow_engine.py) actually reads:
      //   config.get("cron", "") and config.get("schedule_name", "")
      // Neither key was ever written by the UI, so both come back empty —
      // this is the defect: a schedule configured through the UI can never
      // populate the cron expression the engine looks for.
      expect(config.cron).toBeUndefined();
      expect(config.schedule_name).toBeUndefined();
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  test('KNOWN DEFECT: schedule custom-cron field ("cronExpression") also does not match the engine-read key ("cron")', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildTriggerFlow(page, 'rt-trig-sch-cron-api');
      flowId = built.flowId;
      const { canvas, modal, sidebar } = built;
      await modal.selectCard('Schedule');
      await sidebar.fillField('Schedule Type', 'Custom (Cron)');
      await sidebar.fillField('Cron Expression', '15 3 * * *');
      await modal.saveTriggerConfiguration();
      await canvas.settle();
      await canvas.save();

      const defn = await getFlowDefinition(api, flowId);
      const entry = defn.definition_json.nodes.find((n) => n.id === defn.definition_json.entry);
      const config = (entry?.config ?? {}) as Record<string, unknown>;
      // The UI writes the cron string under "cronExpression"...
      expect(config.cronExpression).toBe('15 3 * * *');
      // ...but _exec_trigger_schedule only ever looks at "cron" — so even
      // when the user picks "Custom (Cron)" and types a real cron string,
      // the engine-facing key is still absent.
      expect(config.cron).toBeUndefined();
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  test('doc-event: doctype and event persist and match the exact keys the engine/schema consume', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildTriggerFlow(page, 'rt-trig-de-api');
      flowId = built.flowId;
      const { canvas, modal, sidebar } = built;
      await modal.selectCard('Data');
      await sidebar.fillCombobox('Document Type', 'ToDo');
      await sidebar.fillField('Event Type', 'Delete');
      await modal.saveTriggerConfiguration();
      await canvas.settle();
      await canvas.save();

      const defn = await getFlowDefinition(api, flowId);
      const entry = defn.definition_json.nodes.find((n) => n.id === defn.definition_json.entry);
      expect(entry?.type).toBe('trigger.doc-event');
      const config = (entry?.config ?? {}) as Record<string, unknown>;
      // Unlike webhook/schedule, these two keys ("doctype", "event") DO match
      // what huf/ai/flow_api.py's config_schema advertises and what
      // _exec_trigger_doc_event's surrounding context enrichment reads back
      // out — so at the config-shape level this is not a key-name defect.
      // NOTE (separate, narrower finding, not asserted here): the UI's Event
      // Type options are save/update/delete/before-save/before-update/
      // before-delete, while the config_schema's own "event" options list is
      // after_insert/on_update/on_submit/on_cancel/on_delete (a Frappe
      // doc_event hook name vocabulary) — the two vocabularies don't overlap
      // either, and no run_doc_event_flows()-style hook wiring exists
      // anywhere in this app (huf/ai/flow_engine.py's own comment references
      // "flow_hooks.run_doc_event_flows()", which does not exist in this
      // codebase), so it's unclear anything ever reads config.event to decide
      // whether to fire a doc-event-triggered flow in the first place.
      expect(config.doctype).toBe('ToDo');
      expect(config.event).toBe('delete');
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
});
