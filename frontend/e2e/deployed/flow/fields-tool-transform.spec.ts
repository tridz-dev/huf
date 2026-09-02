import { test, expect, Page, Locator } from '@playwright/test';
import { FlowsListPage } from './FlowsListPage';
import { FlowCanvasPage } from './FlowCanvasPage';
import { NodeModal } from './NodeModal';
import { ConfigSidebar } from './ConfigSidebar';
import { newApiContext, uniqueFlowName, getFlowDefinition } from './flowApi';

/**
 * Point 8, exhaustive for `tool-call` and `transform` — every field the
 * config sidebar renders for these two node types gets its own round-trip
 * test (build flow -> set field -> save -> hard reload -> re-select ->
 * assert). Mirrors fields.spec.ts's per-field pattern and page objects;
 * see that file's header comment for the rationale (one bad selector
 * should not fail every field in a node type).
 *
 * Field inventory (from RightSidebar.tsx):
 *
 * tool-call (config.type === 'tool-call'):
 *   - "Tool" (Combobox, #tool-name)                    -> config.tool_name (+ config.mcp_server)
 *   - Arguments (JsonSchemaForm, schema-driven)         -> config.args[fieldname]
 *       for add_table_row: table_name *, data *, confirm (all render as plain
 *       Inputs here because the persisted Agent Tool Function schema types
 *       every one of these as JSON Schema "string" -- see JsonSchemaForm.tsx
 *       classifyField(): type==='string' -> PrimitiveField, an <Input>).
 *   - "Save Result To Context" (Input, #save-result)   -> config.output.save_result_to_context
 *   - "Attributed Agent (optional)" (Combobox, #tool-call-agent) -> config.agent_name
 *   - "Node Title" is common to every node type and is explicitly out of
 *     scope per the task (also already covered generically elsewhere).
 *
 * transform (config.type === 'transform'):
 *   - repeatable "Transformation #N" rows, added via "+ Add Transformation"
 *     (none exist by default):
 *       - "Source Field" (Input)   -> config.transformations[i].source_field
 *       - "Target Field" (Input)   -> config.transformations[i].target_field
 *       - "Operation" (Select: Copy/Map/Template) -> config.transformations[i].operation
 *         (engine-supported values: copy, map, template)
 *   Row Labels carry no htmlFor, so ConfigSidebar (which drives everything
 *   off htmlFor -> id) cannot address them; driven positionally below.
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

/** Re-select the action node by position (index 1: trigger is 0), never by
 * label -- tool-call's "Node Title" field renames the canvas node, so a
 * label-based lookup breaks the moment that field is under test. */
async function reselectActionNode(page: Page): Promise<void> {
  await page.locator('.react-flow__node').nth(1).click();
}

test.describe('per-field config round-trip: tool-call', () => {
  test('tool-call: "Tool" round-trips', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlow(page, 'Call Tool', 'rt-tool-tool');
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode('Call Tool');
      await sidebar.fillCombobox('Tool', 'add_table_row');
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await reselectActionNode(page);
      const got = await sidebar.readCombobox('Tool');
      expect(got).toContain('add_table_row');

      const def = await getFlowDefinition(api, flowId);
      const node = def.definition_json.nodes.find((n) => n.type === 'tool.call');
      expect((node?.config as { tool_name?: string })?.tool_name).toBe('add_table_row');
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  test('tool-call: "Attributed Agent (optional)" round-trips', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlow(page, 'Call Tool', 'rt-tool-agent');
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode('Call Tool');
      await sidebar.fillCombobox('Attributed Agent (optional)', 'Demo Assistant');
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await reselectActionNode(page);
      const got = await sidebar.readCombobox('Attributed Agent (optional)');
      expect(got).toContain('Demo Assistant');

      const def = await getFlowDefinition(api, flowId);
      const node = def.definition_json.nodes.find((n) => n.type === 'tool.call');
      expect((node?.config as { agent_name?: string })?.agent_name).toBe('Demo Assistant');
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  test('tool-call: "Save Result To Context" round-trips', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildNodeFlow(page, 'Call Tool', 'rt-tool-save');
      flowId = built.flowId;
      const { canvas, sidebar } = built;
      await canvas.selectNode('Call Tool');
      await sidebar.fillField('Save Result To Context', 'tool_result');
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await reselectActionNode(page);
      expect(await sidebar.readField('Save Result To Context')).toBe('tool_result');

      const def = await getFlowDefinition(api, flowId);
      const node = def.definition_json.nodes.find((n) => n.type === 'tool.call');
      expect((node?.config as { output?: { save_result_to_context?: string } })?.output?.save_result_to_context).toBe('tool_result');
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });

  // --- tool-call ARGUMENT fields --------------------------------------
  // Selecting "add_table_row" renders its JSON-Schema-driven argument form.
  // Its persisted schema types table_name/data/confirm all as "string", so
  // every one of them renders as a plain <Input> labeled with the bare
  // fieldname (JsonSchemaForm PrimitiveField). Round-tripped under
  // config.args, excluding "Node Title", "Tool", "Save Result To Context"
  // and "Attributed Agent (optional)" per the task -- those are node/tool
  // config, not tool arguments.
  for (const [label, value] of [
    ['table_name', 'my_table'],
    ['data', '{"title":"Hello","status":"Open"}'],
    ['confirm', 'true'],
  ] as const) {
    test(`tool-call arg: "${label}" round-trips under config.args`, async ({ page, baseURL }) => {
      const api = await newApiContext(new URL(baseURL!).origin);
      let flowId: string | undefined;
      try {
        const built = await buildNodeFlow(page, 'Call Tool', 'rt-tool-arg');
        flowId = built.flowId;
        const { canvas, sidebar } = built;
        await canvas.selectNode('Call Tool');
        await sidebar.fillCombobox('Tool', 'add_table_row');
        await canvas.settle();
        await sidebar.fillField(label, value);
        await canvas.settle();
        await canvas.save();
        await canvas.reload();
        await canvas.settle();
        await reselectActionNode(page);
        // Tool details (and thus the argument form) refetch after reload;
        // wait for the field to actually appear before reading it.
        await expect(page.locator('label', { hasText: label }).first()).toBeVisible({ timeout: 30000 });
        expect(await sidebar.readField(label)).toBe(value);

        const def = await getFlowDefinition(api, flowId);
        const node = def.definition_json.nodes.find((n) => n.type === 'tool.call');
        const args = (node?.config as { args?: Record<string, unknown> })?.args || {};
        expect(args[label]).toBe(value);
      } finally {
        if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
        await api.dispose();
      }
    });
  }
});

test.describe('per-field config round-trip: transform', () => {
  /**
   * Locate a "Transformation #N" row. Its heading `<span>` and its Source
   * Field / Target Field / Operation controls are siblings/descendants of
   * one wrapping `<div className="p-3 ... space-y-2">` -- but every `div`
   * ancestor up to the sidebar root also (transitively) contains both the
   * heading text and *some* input, so filtering on "contains heading text
   * AND contains an input" alone is ambiguous. Because nested elements are
   * always returned after their ancestors in Playwright's DOM-order
   * locator lists, `.last()` on that filtered set yields the innermost
   * (and therefore correct, most specific) row wrapper -- the ancestor
   * chain's deepest link still satisfying both conditions.
   */
  function rowLocator(page: Page, index: number): Locator {
    const heading = `Transformation #${index + 1}`;
    return page
      .locator('div')
      .filter({ hasText: heading })
      .filter({ has: page.locator('input') })
      .last();
  }

  async function addTransformationRow(page: Page): Promise<void> {
    await page.getByRole('button', { name: /\+ Add Transformation/i }).click();
  }

  async function buildTransformFlow(page: Page, prefix: string) {
    const built = await buildNodeFlow(page, 'Transform Data', prefix);
    await built.canvas.selectNode('Transform Data');
    return built;
  }

  for (const [fieldIndex, label, value] of [
    [0, 'Source Field', 'api_response.data'],
    [1, 'Target Field', 'processed_data'],
  ] as const) {
    test(`transform row: "${label}" round-trips`, async ({ page, baseURL }) => {
      const api = await newApiContext(new URL(baseURL!).origin);
      let flowId: string | undefined;
      try {
        const built = await buildTransformFlow(page, 'rt-xform-field');
        flowId = built.flowId;
        const { canvas } = built;
        await addTransformationRow(page);
        await canvas.settle();
        const row = rowLocator(page, 0);
        await row.locator('input').nth(fieldIndex).fill(value);
        await canvas.settle();
        await canvas.save();
        await canvas.reload();
        await canvas.settle();
        await reselectActionNode(page);

        const reRow = rowLocator(page, 0);
        expect(await reRow.locator('input').nth(fieldIndex).inputValue()).toBe(value);

        const def = await getFlowDefinition(api, flowId);
        const node = def.definition_json.nodes.find((n) => n.type === 'transform');
        const t = ((node?.config as { transformations?: Array<Record<string, unknown>> })?.transformations || [])[0];
        const key = fieldIndex === 0 ? 'source_field' : 'target_field';
        expect(t?.[key]).toBe(value);
      } finally {
        if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
        await api.dispose();
      }
    });
  }

  test('transform row: "Operation" round-trips and offers {Copy, Map, Template}', async ({ page, baseURL }) => {
    const api = await newApiContext(new URL(baseURL!).origin);
    let flowId: string | undefined;
    try {
      const built = await buildTransformFlow(page, 'rt-xform-op');
      flowId = built.flowId;
      const { canvas } = built;
      await addTransformationRow(page);
      await canvas.settle();
      const row = rowLocator(page, 0);
      const trigger = row.locator('button[role="combobox"]').first();
      await trigger.click();
      const optionTexts = (await page.getByRole('option').allInnerTexts()).map((t) => t.trim());
      expect(optionTexts.sort()).toEqual(['Copy', 'Map', 'Template'].sort());
      await page.getByRole('option', { name: 'Map' }).click();
      await canvas.settle();
      await canvas.save();
      await canvas.reload();
      await canvas.settle();
      await reselectActionNode(page);

      const reRow = rowLocator(page, 0);
      const reTrigger = reRow.locator('button[role="combobox"]').first();
      expect((await reTrigger.innerText()).trim()).toBe('Map');

      const def = await getFlowDefinition(api, flowId);
      const node = def.definition_json.nodes.find((n) => n.type === 'transform');
      const t = ((node?.config as { transformations?: Array<Record<string, unknown>> })?.transformations || [])[0];
      expect(t?.operation).toBe('map');
    } finally {
      if (flowId) await api.delete(`/api/resource/Flow Definition/${flowId}`).catch(() => {});
      await api.dispose();
    }
  });
});
