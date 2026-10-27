import { test, expect, Page } from '@playwright/test';
import { goto, mockOfflineApis } from './helpers';
import {
  callsOf,
  makeNumberSummary,
  makeRouteDecision,
  makeSolutionOverview,
  makeSolutionSummary,
  mockSolutionResources,
  mockSolutionsApi,
  solutionsError,
  type SolutionsMockOptions,
} from './helpers/solutionsMocks';

/** New solution wizard (/solutions/new) against a fully mocked backend. Nothing is saved until Go live. */

const MGMT = '**/api/method/huf.ai.whatsapp.management.';

const tpl = (template_name: string, over: Record<string, unknown> = {}) => ({
  name: `tpl-${template_name}`, template_name, category: 'UTILITY', language_code: 'en_US', status: 'APPROVED',
  template: `Body of ${template_name}`, shared: false, used_by: [], owner: null, ...over,
});

const TEMPLATES = [
  tpl('a_other_template'),
  tpl('order_ready_pickup', { shared: true, used_by: [{ solution: 'care', title: 'Care desk' }, { solution: 'promo', title: 'Promo blast' }] }),
  tpl('weekend_croissant_special'),
  tpl('pending_one', { status: 'PENDING' }),
];

async function setup(page: Page, handlers: SolutionsMockOptions['handlers'] = {}) {
  await mockOfflineApis(page);
  await mockSolutionResources(page, { flows: [{ name: 'care-flow', flow_name: 'Care flow' }] });
  const calls = await mockSolutionsApi(page, {
    numberSummaries: {
      'GW-1': makeNumberSummary({
        solutions: [{ name: 'care', title: 'Care desk', status: 'Live', usage_pct: 10, sends_24h: 10 }],
        quality: { rating: 'GREEN', source: 'meta' },
      }),
      'GW-2': makeNumberSummary({ gateway: 'GW-2', label: 'Catering line', phone: '+1 555 0200' }),
    },
    overviews: {
      'new-solution': makeSolutionOverview({ name: 'new-solution', title: 'Order desk', status: 'Live' }),
      'new-paused': makeSolutionOverview({ name: 'new-paused', title: 'Shop FAQ', status: 'Paused', primary: null }),
    },
    handlers,
  });
  await page.route(`${MGMT}list_templates{,?*}`, (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ message: { success: true, templates: TEMPLATES } }) }),
  );
  return calls;
}

const next = (page: Page) => page.getByRole('button', { name: 'Continue' }).click();
const step = (page: Page, n: number) => expect(page.getByRole('list', { name: 'Steps' }).locator('[aria-current="step"]')).toContainText(`${n}.`);

test.describe('New solution wizard', () => {
  test('happy path for an intent: prefilled, keywords, suggested templates, test, go live', async ({ page }) => {
    const calls = await setup(page, {
      simulate_route: ({ parsed }) =>
        makeRouteDecision({
          solution: parsed.request.draft.title, agent: null, reason: 'keyword',
          trace: [{ k: 'win', t: `Draft keyword matched ${parsed.request.draft.title}` }],
        }),
      create_solution: ({ parsed }) => makeSolutionSummary({ name: 'new-solution', title: parsed.payload.title, status: 'Paused' }),
    });
    await goto(page, '/solutions/new?purpose=orders');

    // Step 1: name prefilled from the purpose, first number chosen, sharing explained.
    await step(page, 1);
    await expect(page.getByLabel('Name')).toHaveValue('Order desk');
    await expect(page.getByRole('button', { name: /^Take orders/ })).toHaveAttribute('aria-pressed', 'true');
    const gw1 = page.getByTestId('gateway-GW-1');
    await expect(gw1).toHaveAttribute('aria-pressed', 'true');
    await expect(gw1).toContainText('Already used by Care desk. Sharing is fine.');
    await expect(page.getByTestId('gateway-GW-2')).toContainText('Nobody uses it yet.');
    await page.getByLabel('Answered by').selectOption({ label: 'Order agent (agent)' });
    await next(page);

    // Step 2: keyword chips from the purpose, editable.
    await step(page, 2);
    await expect(page.getByText('Suggested for Take orders:')).toBeVisible();
    await expect(page.getByText('Another solution already answers on this number')).toBeVisible();
    for (const k of ['order', 'menu', 'cake']) await expect(page.getByRole('button', { name: `Remove ${k}` })).toBeVisible();
    await page.getByRole('button', { name: 'Remove cake' }).click();
    await expect(page.getByRole('button', { name: 'Remove cake' })).toHaveCount(0);
    await page.getByLabel('Keywords (message contains)').fill('Pickup');
    await page.getByLabel('Keywords (message contains)').press('Enter');
    await expect(page.getByRole('button', { name: 'Remove pickup' })).toBeVisible();
    await expect(page.getByLabel('Ad or link tag')).toHaveValue('weekend_special');
    await expect(page.getByTestId('customer-preview')).toContainText('Reply with a word like order to reach Order desk.');
    await next(page);

    // Step 3: suggested templates come first, and are preselected; pending ones are not offered.
    await step(page, 3);
    const options = page.locator('button[aria-pressed]');
    await expect(options.nth(0)).toContainText('order_ready_pickup');
    await expect(options.nth(0)).toContainText('Suggested');
    await expect(options.nth(0)).toContainText('Shared');
    await expect(options.nth(0)).toContainText('Care desk');
    await expect(options.nth(0)).toContainText('Promo blast');
    await expect(options.nth(0)).toContainText('Using');
    await expect(options.nth(1)).toContainText('weekend_croissant_special');
    await expect(options.nth(1)).toContainText('Using');
    await expect(options.nth(2)).toContainText('a_other_template');
    await expect(options.nth(2)).toContainText('Add');
    await expect(page.getByText('pending_one')).toHaveCount(0);
    await options.nth(2).click();
    await expect(options.nth(2)).toContainText('Using');
    await expect(page.getByText('We suggest these settings for Take orders')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Review on Main counter' })).toHaveAttribute('href', /\/whatsapp\?gateway=GW-1&tab=settings/);
    await next(page);

    // Step 4: the test chat sends the draft (nothing saved yet).
    await step(page, 4);
    expect(callsOf(calls, 'create_solution')).toHaveLength(0);
    await expect(page.getByTestId('no-target-note')).toHaveCount(0);
    await page.getByRole('button', { name: 'a order for friday' }).click();
    await expect(page.getByText('Routed to Order desk')).toBeVisible();
    await expect(page.getByLabel('Routing trace')).toContainText('Draft keyword matched Order desk');
    const sim = callsOf(calls, 'simulate_route');
    expect(sim).toHaveLength(1);
    expect(sim[0].parsed.request).toMatchObject({
      gateway: 'GW-1', text: 'a order for friday', state: {},
      draft: {
        title: 'Order desk', gateway: 'GW-1', intent: 'orders', inbound: true, catch_all: false,
        entries: [
          { match_type: 'Keyword', match_values: ['order', 'menu', 'pickup'] },
          { match_type: 'Ad or link tag', match_values: ['weekend_special'] },
        ],
      },
    });
    await page.getByRole('button', { name: 'Tap ad weekend_special' }).click();
    await expect.poll(() => callsOf(calls, 'simulate_route').length).toBe(2);
    expect(callsOf(calls, 'simulate_route')[1].parsed.request).toMatchObject({ ref: 'weekend_special', draft: { title: 'Order desk' } });
    expect(callsOf(calls, 'create_solution')).toHaveLength(0);

    // Go live: create_solution, then go_live, then the detail page.
    await page.getByRole('button', { name: 'Go live' }).click();
    await expect(page).toHaveURL(/\/huf\/solutions\/new-solution$/);
    await expect(page.getByRole('tab', { name: 'Overview' })).toBeVisible();
    const order = calls.filter((c) => ['create_solution', 'go_live'].includes(c.method)).map((c) => c.method);
    expect(order).toEqual(['create_solution', 'go_live']);
    expect(callsOf(calls, 'create_solution')[0].parsed.payload).toEqual({
      title: 'Order desk', mode: 'intent', purpose: 'orders', existing_target: { type: 'Agent', name: 'order-agent' },
      gateway: 'GW-1',
      entries: [
        { match_type: 'Keyword', match_values: ['order', 'menu', 'pickup'] },
        { match_type: 'Ad or link tag', match_values: ['weekend_special'] },
      ],
      inbound: true,
      templates: ['order_ready_pickup', 'weekend_croissant_special', 'a_other_template'],
      test_mode: false,
    });
    expect(callsOf(calls, 'go_live')[0].args.name).toBe('new-solution');
    await expect(page.getByText('Order desk is live')).toBeVisible();
  });

  test('a purpose with no inbound shows the note until entry points are added anyway', async ({ page }) => {
    const calls = await setup(page);
    await goto(page, '/solutions/new?purpose=updates');
    await expect(page.getByLabel('Name')).toHaveValue('Order updates');
    await next(page);
    await expect(page.getByTestId('none-inbound-note')).toContainText('Nobody can start a chat with this solution.');
    await expect(page.getByLabel('Keywords (message contains)')).toHaveCount(0);

    // Leaving it as is saves an outbound-only solution.
    await next(page);
    await next(page);
    await page.getByRole('button', { name: 'Go live' }).click();
    await expect(page).toHaveURL(/\/solutions\/new-solution$/);
    expect(callsOf(calls, 'create_solution')[0].parsed.payload).toMatchObject({ purpose: 'updates', inbound: false, entries: [] });
  });

  test('"Add entry points anyway" brings the inbound form back', async ({ page }) => {
    const calls = await setup(page);
    await goto(page, '/solutions/new?purpose=updates');
    await next(page);
    await page.getByRole('button', { name: 'Add entry points anyway' }).click();
    await expect(page.getByTestId('none-inbound-note')).toHaveCount(0);
    await page.getByLabel('Keywords (message contains)').fill('status');
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    await next(page);
    await next(page);
    await page.getByRole('button', { name: 'Go live' }).click();
    await expect(page).toHaveURL(/\/solutions\/new-solution$/);
    expect(callsOf(calls, 'create_solution')[0].parsed.payload).toMatchObject({
      inbound: true, entries: [{ match_type: 'Keyword', match_values: ['status'] }],
    });
  });

  test('without an agent or flow it explains and saves paused (no go_live)', async ({ page }) => {
    const calls = await setup(page, {
      create_solution: ({ parsed }) => makeSolutionSummary({ name: 'new-paused', title: parsed.payload.title, status: 'Paused' }),
    });
    await goto(page, '/solutions/new?purpose=answer');
    await expect(page.getByLabel('Name')).toHaveValue('Shop FAQ');
    await expect(page.getByLabel('Answered by')).toHaveValue('');
    await expect(page.getByText('Without one, the solution is saved as paused.')).toBeVisible();
    await next(page);
    await next(page);
    await next(page);
    await expect(page.getByTestId('no-target-note')).toContainText('No agent or flow is chosen: it will be saved as paused until you choose one.');
    await page.getByRole('button', { name: 'Go live' }).click();
    await expect(page).toHaveURL(/\/solutions\/new-paused$/);
    await expect(page.getByText('Shop FAQ saved as paused. Choose what answers to take it live.')).toBeVisible();
    expect(callsOf(calls, 'create_solution')).toHaveLength(1);
    expect(callsOf(calls, 'create_solution')[0].parsed.payload.existing_target).toBeUndefined();
    expect(callsOf(calls, 'go_live')).toHaveLength(0);
    // The catch-all purpose sends a catch-all entry.
    expect(callsOf(calls, 'create_solution')[0].parsed.payload.entries).toEqual([{ match_type: 'Catch-all', match_values: [] }]);
  });

  test('test mode saves without going live', async ({ page }) => {
    const calls = await setup(page);
    await goto(page, '/solutions/new?purpose=orders');
    await page.getByLabel('Answered by').selectOption({ label: 'Care flow (flow)' });
    await next(page);
    await next(page);
    await next(page);
    await page.getByLabel(/Keep it in test mode after saving/).check();
    await page.getByRole('button', { name: 'Go live' }).click();
    await expect(page).toHaveURL(/\/solutions\/new-solution$/);
    expect(callsOf(calls, 'create_solution')[0].parsed.payload).toMatchObject({
      existing_target: { type: 'Flow', name: 'care-flow' }, test_mode: true,
    });
    expect(callsOf(calls, 'go_live')).toHaveLength(0);
    await expect(page.getByText('Order desk saved in test mode')).toBeVisible();
  });

  test('a draft template is sent as draft_template', async ({ page }) => {
    const calls = await setup(page);
    await goto(page, '/solutions/new?purpose=orders');
    await page.getByLabel('Answered by').selectOption({ label: 'Order agent (agent)' });
    await next(page);
    await next(page);
    await page.getByRole('button', { name: /Draft a new template/ }).click();
    await expect(page.getByRole('button', { name: /Draft a new template/ })).toContainText('order_desk_quote');
    await next(page);
    await page.getByRole('button', { name: 'Go live' }).click();
    await expect(page).toHaveURL(/\/solutions\/new-solution$/);
    expect(callsOf(calls, 'create_solution')[0].parsed.payload.draft_template).toEqual({
      name: 'order_desk_quote', language: 'en', category: 'UTILITY', status: 'Draft',
    });
  });

  test('a save error stays on the wizard with the explanation', async ({ page }) => {
    const calls = await setup(page, {
      create_solution: () => solutionsError('invalid_payload', 'Title is already used.'),
    });
    await goto(page, '/solutions/new?purpose=orders');
    await page.getByLabel('Answered by').selectOption({ label: 'Order agent (agent)' });
    await next(page);
    await next(page);
    await next(page);
    await page.getByRole('button', { name: 'Go live' }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'Some details are not valid.' })).toContainText('Title is already used.');
    await expect(page).toHaveURL(/\/solutions\/new/);
    expect(callsOf(calls, 'go_live')).toHaveLength(0);
    await expect(page.getByRole('button', { name: 'Go live' })).toBeEnabled();
  });

  test('a name is required, and Back keeps what was typed', async ({ page }) => {
    await setup(page);
    await goto(page, '/solutions/new?mode=blank');
    await expect(page.getByLabel('Name')).toHaveValue('');
    await expect(page.getByRole('button', { name: 'Continue' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Back' })).toBeDisabled();
    await page.getByLabel('Name').fill('Walk-in orders');
    await expect(page.getByRole('button', { name: 'Continue' })).toBeEnabled();
    await next(page);
    await step(page, 2);
    await expect(page.getByTestId('customer-preview')).toContainText('Messages that no other rule catches reach Walk-in orders.');
    await page.getByRole('button', { name: 'Back' }).click();
    await expect(page.getByLabel('Name')).toHaveValue('Walk-in orders');
  });

  test('"existing" mode: preselected agent goes live with existing_target', async ({ page }) => {
    const calls = await setup(page);
    await goto(page, '/solutions/new?mode=existing');
    await page.getByLabel('Name').fill('Existing agent line');
    await next(page);
    await next(page);
    await next(page);
    await page.getByRole('button', { name: 'Go live' }).click();
    await expect(page).toHaveURL(/\/solutions\/new-solution$/);
    expect(callsOf(calls, 'create_solution')[0].parsed.payload).toMatchObject({
      mode: 'existing', existing_target: { type: 'Agent', name: 'order-agent' },
    });
    expect(callsOf(calls, 'go_live')).toHaveLength(1);
  });

  test('"existing" mode: the agent shown as chosen is really chosen', async ({ page }) => {
    await setup(page);
    await goto(page, '/solutions/new?mode=existing');
    await expect(page.getByLabel('Answered by')).toHaveValue('Agent:order-agent');
    await page.getByLabel('Name').fill('Existing agent line');
    await expect(page.getByRole('button', { name: 'Continue' })).toBeEnabled();
  });

  test('switching number clears the picked templates and loads the other account', async ({ page }) => {
    const tcalls: string[] = [];
    await setup(page);
    await page.route(`${MGMT}list_templates{,?*}`, (route) => {
      const r = route.request();
      const raw = r.postData();
      const args = raw ? JSON.parse(raw) : Object.fromEntries(new URL(r.url()).searchParams);
      tcalls.push(String(args.gateway_name));
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ message: { success: true, templates: TEMPLATES } }) });
    });
    await goto(page, '/solutions/new?purpose=orders');
    await page.getByTestId('gateway-GW-2').click();
    await expect(page.getByTestId('gateway-GW-2')).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => tcalls).toContain('GW-2');
    await next(page);
    await next(page);
    await expect(page.getByText('Used by').first()).toBeVisible();
    await expect(page.locator('button[aria-pressed="true"]')).toHaveCount(0);
  });

  test('?gateway= preselects the number', async ({ page }) => {
    await setup(page);
    await goto(page, '/solutions/new?gateway=GW-2&purpose=orders');
    await expect(page.getByTestId('gateway-GW-2')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByTestId('gateway-GW-1')).toHaveAttribute('aria-pressed', 'false');
  });
});
