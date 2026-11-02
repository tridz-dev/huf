import { test, expect, Page } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';
import {
  GW1,
  callsOf,
  makeEntryPoint,
  makeRouteDecision,
  makeSolutionOverview,
  makeSolutionSummary,
  mockSolutionResources,
  mockSolutionsApi,
  solutionsError,
  type SolutionsMockOptions,
} from './helpers/solutionsMocks';

/**
 * Solutions pages (/solutions, /solutions/:name) against a fully mocked backend.
 * The wizard lives in solutions-wizard.spec.ts; the WhatsApp page changes in whatsapp.spec.ts.
 */

const MGMT = '**/api/method/huf.ai.whatsapp.management.';

const orders = makeSolutionSummary();
const care = makeSolutionSummary({
  name: 'care', title: 'Care desk', purpose: 'support', shared: true, chats_7d: 3, description: 'Handles problems.',
  primary: { type: 'Flow', name: 'care-flow', label: 'Care flow' }, runs_on: [GW1, { gateway: 'GW-2', label: 'Catering line', phone: '+1 555 0200' }],
});
const promo = makeSolutionSummary({ name: 'promo', title: 'Promo blast', purpose: 'updates', status: 'Paused', chats_7d: 0, description: '' });

async function setup(page: Page, opts: SolutionsMockOptions = {}) {
  await mockOfflineApis(page);
  await mockSolutionResources(page);
  return mockSolutionsApi(page, { solutions: [orders, care, promo], ...opts });
}

/** Management calls the embedded Templates tab makes. */
async function mockTemplates(page: Page, templates: unknown[] = []) {
  const calls: Array<{ method: string; args: Record<string, unknown> }> = [];
  for (const [method, body] of [
    ['list_templates', { success: true, templates }],
    ['list_template_drafts', { success: true, drafts: [] }],
  ] as const) {
    await page.route(`${MGMT}${method}{,?*}`, (route) => {
      const r = route.request();
      const raw = r.postData();
      const args = raw ? (JSON.parse(raw) as Record<string, unknown>) : Object.fromEntries(new URL(r.url()).searchParams);
      calls.push({ method, args });
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ message: body }) });
    });
  }
  return calls;
}

test.describe('Solutions list and navigation', () => {
  test('the nav shows Solutions right after Chat and routes to /solutions', async ({ page }) => {
    await setup(page);
    await goto(page, '/');
    const nav = page.locator('[data-sidebar="sidebar"]').first();
    const hrefs = await nav.locator('a[href]').evaluateAll((els) => els.map((e) => e.getAttribute('href')));
    const chat = hrefs.indexOf('/huf/chat');
    expect(chat).toBeGreaterThanOrEqual(0);
    expect(hrefs[chat + 1]).toBe('/huf/solutions');
    await expect(nav.locator('a[href="/huf/solutions"]')).toContainText('Solutions');
    await nav.locator('a[href="/huf/solutions"]').click();
    await expect(page).toHaveURL(/\/huf\/solutions$/);
    await expect(page.getByRole('heading', { name: 'Active solutions' })).toBeVisible();
  });

  test('the list renders cards with purpose, numbers, shared pill and status', async ({ page }) => {
    await setup(page);
    await goto(page, '/solutions');
    await waitForContent(page);
    await expect(page.getByText('Order desk', { exact: true })).toBeVisible();
    await expect(page.getByText('Care desk', { exact: true })).toBeVisible();
    await expect(page.getByText('Promo blast', { exact: true })).toBeVisible();
    // Labels and values come from the card metadata.
    await expect(page.getByText('Purpose').first()).toBeVisible();
    await expect(page.getByText('Runs on').first()).toBeVisible();
    await expect(page.getByText('Take orders', { exact: true })).toBeVisible();
    await expect(page.getByText('Support & handoff', { exact: true })).toBeVisible();
    await expect(page.getByText('Main counter', { exact: true })).toHaveCount(3);
    await expect(page.getByText('Catering line', { exact: true })).toBeVisible();
    await expect(page.getByText('Shared', { exact: true })).toHaveCount(1);
    await expect(page.getByText('Active', { exact: true })).toHaveCount(2);
    await expect(page.getByText('Paused', { exact: true })).toHaveCount(1);
    await expect(page.getByText('12 chats this week')).toBeVisible();
  });

  test('the Any purpose filter calls the API with the chosen purpose', async ({ page }) => {
    const calls = await setup(page);
    await goto(page, '/solutions');
    await expect(page.getByText('Care desk', { exact: true })).toBeVisible();
    const filter = page.getByRole('combobox', { name: 'Purpose' });
    await expect(filter).toContainText('Any purpose');
    await filter.click();
    await page.getByRole('option', { name: 'Support & handoff' }).click();
    await expect.poll(() => callsOf(calls, 'list_solutions').map((c) => c.args.purpose ?? null)).toContain('support');
    await expect(page.getByText('Care desk', { exact: true })).toBeVisible();
    await expect(page.getByText('Order desk', { exact: true })).toHaveCount(0);
    await filter.click();
    await page.getByRole('option', { name: 'Any purpose' }).click();
    await expect(page.getByText('Order desk', { exact: true })).toBeVisible();
  });

  test('a purpose with no solutions shows the filtered empty message', async ({ page }) => {
    await setup(page);
    await goto(page, '/solutions');
    await page.getByRole('combobox', { name: 'Purpose' }).click();
    await page.getByRole('option', { name: 'Bookings' }).click();
    await expect(page.getByText('No solutions for this purpose')).toBeVisible();
  });

  test('a failing list call shows an error with Try again', async ({ page }) => {
    let first = true;
    await setup(page, {
      handlers: {
        list_solutions: () => {
          if (first) { first = false; return solutionsError('not_permitted', 'You may not list solutions.'); }
          return [orders];
        },
      },
    });
    await goto(page, '/solutions');
    await expect(page.getByRole('alert')).toContainText('You may not list solutions.');
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect(page.getByText('Order desk', { exact: true })).toBeVisible();
  });

  test('first time: six purposes and the two exit links; a purpose opens the wizard', async ({ page }) => {
    await setup(page, { solutions: [] });
    await goto(page, '/solutions');
    await expect(page.getByRole('heading', { name: 'Group what your WhatsApp numbers do' })).toBeVisible();
    for (const name of ['Answer questions', 'Take orders', 'Support & handoff', 'Bookings', 'Send updates', 'Team & internal']) {
      await expect(page.getByRole('button', { name: new RegExp(`^${name.replace('&', '\\&')}`) })).toBeVisible();
    }
    await expect(page.getByRole('button', { name: 'I already have an agent or flow' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start blank' })).toBeVisible();
    await expect(page.getByText('Connected numbers reply to no one until a solution is live.')).toBeVisible();

    await page.getByRole('button', { name: /^Take orders/ }).click();
    await expect(page).toHaveURL(/\/huf\/solutions\/new\?purpose=orders$/);
    await expect(page.getByLabel('Name')).toHaveValue('Order desk');
  });

  test('first time: the exit links open the wizard in existing and blank mode', async ({ page }) => {
    await setup(page, { solutions: [] });
    await goto(page, '/solutions');
    await page.getByRole('button', { name: 'I already have an agent or flow' }).click();
    await expect(page).toHaveURL(/\/solutions\/new\?mode=existing$/);
    await goto(page, '/solutions');
    await page.getByRole('button', { name: 'Start blank' }).click();
    await expect(page).toHaveURL(/\/solutions\/new\?mode=blank$/);
  });

  test('clicking a card opens the detail page', async ({ page }) => {
    await setup(page, { overviews: { orders: makeSolutionOverview() } });
    await goto(page, '/solutions');
    await page.getByText('Order desk', { exact: true }).click();
    await expect(page).toHaveURL(/\/huf\/solutions\/orders$/);
    await expect(page.getByRole('tab', { name: 'Overview' })).toHaveAttribute('data-state', 'active');
  });
});

test.describe('Solution detail', () => {
  test('overview band: ok says it is working', async ({ page }) => {
    await setup(page, { overviews: { orders: makeSolutionOverview() } });
    await goto(page, '/solutions/orders');
    const band = page.getByRole('status').filter({ hasText: 'Working' });
    await expect(band).toContainText('Order desk is routing and replying normally.');
    for (const tab of ['Overview', 'Entry points', 'Templates', 'Conversations', 'Test chat']) {
      await expect(page.getByRole('tab', { name: tab })).toBeVisible();
    }
  });

  test('overview band: warn names the number and blames the busiest solution', async ({ page }) => {
    const calls = await setup(page, {
      overviews: {
        orders: makeSolutionOverview({
          health: { state: 'warn', gateway: 'GW-1', quality: 'Medium', blame: { solution: 'promo', share_pct: 91 } },
        }),
      },
    });
    await goto(page, '/solutions/orders');
    const band = page.getByRole('status').filter({ hasText: 'Warning on' });
    await expect(band).toContainText('Warning on Main counter +1 555 0100. Quality rating: Medium.');
    await expect(band).toContainText("Most of today's sends came from Promo blast (91% of sends in the last 24 hours).");
    await expect(band.getByRole('link', { name: 'Promo blast' })).toHaveAttribute('href', /\/solutions\/promo$/);
    const before = callsOf(calls, 'get_solution_overview').length;
    await band.getByRole('button', { name: 'Check now' }).click();
    await expect.poll(() => callsOf(calls, 'get_solution_overview').length).toBeGreaterThan(before);
  });

  test('an unknown solution shows the not found notice', async ({ page }) => {
    await setup(page, { overviews: {} });
    await goto(page, '/solutions/ghost');
    await expect(page.getByRole('alert')).toContainText('Solution not found');
    await page.getByRole('button', { name: 'Back to solutions' }).click();
    await expect(page).toHaveURL(/\/huf\/solutions$/);
  });

  test('entry points: lists rules per number and the sheet locks the slider at the ceiling', async ({ page }) => {
    const calls = await setup(page, {
      overviews: { orders: makeSolutionOverview() },
      entries: { orders: [makeEntryPoint(), makeEntryPoint({ name: 'ep-2', priority: 2, match_type: 'Catch-all', match_values: [], cap_per_day: null })] },
    });
    await goto(page, '/solutions/orders?tab=entries');
    const section = page.getByRole('region', { name: 'Entry points on Main counter' });
    await expect(section).toContainText('Message contains order');
    await expect(section).toContainText('Any message nobody else claims');
    await section.getByRole('row', { name: /Message contains order/ }).getByRole('button', { name: 'Edit' }).click();

    const sheet = page.getByRole('dialog');
    await expect(sheet.getByText('Maximum 100, set on Main counter')).toBeVisible();
    const slider = sheet.getByRole('slider');
    await expect(slider).toHaveAttribute('aria-valuemax', '100');
    await expect(slider).toHaveAttribute('aria-valuenow', '30');
    await expect(sheet.getByLabel('Daily messages it may start').and(page.locator('input'))).toHaveAttribute('max', '100');
    // The slider cannot go above the ceiling.
    await slider.focus();
    await page.keyboard.press('End');
    await expect(slider).toHaveAttribute('aria-valuenow', '100');
    await page.keyboard.press('ArrowRight');
    await expect(slider).toHaveAttribute('aria-valuenow', '100');

    await sheet.getByRole('button', { name: 'Save' }).click();
    await expect.poll(() => callsOf(calls, 'save_entry_point').length).toBe(1);
    expect(callsOf(calls, 'save_entry_point')[0].args.solution).toBe('orders');
    expect(callsOf(calls, 'save_entry_point')[0].parsed.entry).toMatchObject({ name: 'ep-1', gateway: 'GW-1', cap_per_day: 100 });
    await expect(sheet).toHaveCount(0);
  });

  test('entry points: a number without a limit has no slider', async ({ page }) => {
    await setup(page, {
      overviews: { orders: makeSolutionOverview({ cost: { sends_24h: 0, cap_share: 0, ceiling: null } }) },
      entries: { orders: [makeEntryPoint({ ceiling: null, ceiling_source: 'none' })] },
    });
    await goto(page, '/solutions/orders?tab=entries');
    await page.getByRole('row', { name: /Message contains order/ }).getByRole('button', { name: 'Edit' }).click();
    const sheet = page.getByRole('dialog');
    await expect(sheet.getByText(/No limit is set on this number/)).toBeVisible();
    await expect(sheet.getByRole('slider')).toHaveCount(0);
  });

  test('entry points: cap_exceeds_ceiling is shown inline and the sheet stays open', async ({ page }) => {
    await setup(page, {
      overviews: { orders: makeSolutionOverview() },
      entries: { orders: [makeEntryPoint()] },
      handlers: { save_entry_point: () => solutionsError('cap_exceeds_ceiling', 'Cap 500 is above the number limit of 100.') },
    });
    await goto(page, '/solutions/orders?tab=entries');
    await page.getByRole('row', { name: /Message contains order/ }).getByRole('button', { name: 'Edit' }).click();
    const sheet = page.getByRole('dialog');
    await sheet.getByLabel('Daily messages it may start').and(page.locator('input')).fill('500');
    await sheet.getByRole('button', { name: 'Save' }).click();
    const alert = sheet.getByRole('alert');
    await expect(alert).toHaveAttribute('data-code', 'cap_exceeds_ceiling');
    await expect(alert).toContainText("That is above this number's daily limit.");
    await expect(alert).toContainText('Cap 500 is above the number limit of 100.');
    await expect(sheet).toBeVisible();
  });

  test('entry points: add a keyword entry point', async ({ page }) => {
    const calls = await setup(page, { overviews: { orders: makeSolutionOverview() }, entries: { orders: [] } });
    await goto(page, '/solutions/orders?tab=entries');
    await page.getByRole('button', { name: 'Add entry point' }).click();
    const sheet = page.getByRole('dialog');
    await sheet.getByLabel('Values').fill('menu, cake');
    await sheet.getByRole('button', { name: 'Save' }).click();
    await expect.poll(() => callsOf(calls, 'save_entry_point').length).toBe(1);
    expect(callsOf(calls, 'save_entry_point')[0].parsed.entry).toMatchObject({ match_type: 'Keyword', match_values: ['menu', 'cake'], gateway: 'GW-1' });
  });

  test('templates tab is scoped to the solution', async ({ page }) => {
    await setup(page, { overviews: { orders: makeSolutionOverview() } });
    const tcalls = await mockTemplates(page, [
      { name: 'tpl-1', template_name: 'order_ready_pickup', category: 'UTILITY', language_code: 'en_US', status: 'APPROVED', template: 'Order ready', shared: false, used_by: [{ solution: 'orders', title: 'Order desk' }], owner: { solution: 'orders', title: 'Order desk' } },
    ]);
    await goto(page, '/solutions/orders?tab=templates');
    await expect(page.getByText('order_ready_pickup').first()).toBeVisible();
    expect(tcalls.filter((c) => c.method === 'list_templates').map((c) => [c.args.gateway_name, c.args.solution])).toContainEqual(['GW-1', 'orders']);
    // Account-level actions are hidden in the scoped view.
    await expect(page.getByRole('button', { name: 'Sync' })).toHaveCount(0);
    await expect(page.getByRole('tab', { name: /Drafts awaiting approval/ })).toHaveCount(0);
    await expect(page.getByRole('combobox', { name: 'Filter by solution' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: /Channels > Templates/ })).toHaveAttribute('href', /\/channels\/whatsapp\/n\/GW-1\/templates/);
  });

  test('conversations tab filters between this solution and all inboxes', async ({ page }) => {
    const calls = await setup(page, {
      overviews: { orders: makeSolutionOverview() },
      conversations: [
        { contact: '+15551230001', preview: 'two croissants please', solution: 'orders', gateway: 'GW-1', ts: '2026-10-24T09:00:00Z' },
      ],
    });
    await goto(page, '/solutions/orders?tab=convs');
    await expect(page.getByText('two croissants please')).toBeVisible();
    await expect.poll(() => callsOf(calls, 'list_solution_conversations').map((c) => c.args.solution ?? null)).toContain('orders');
    await page.getByLabel('Show').selectOption('all');
    await expect.poll(() => callsOf(calls, 'list_solution_conversations').map((c) => c.args.solution ?? null)).toContain(null);
  });

  test('test chat: pin, keyword beats pin and hand-off', async ({ page }) => {
    const decide = (req: { text: string; keyword_beats_pin?: boolean; state: { pin?: { solution: string } } }) => {
      const keywordCare = /help/.test(req.text);
      const pinned = req.state.pin?.solution;
      const winner = pinned && !(keywordCare && req.keyword_beats_pin) ? pinned : keywordCare ? 'care' : 'orders';
      const reason = pinned && winner === pinned ? 'pin' : 'keyword';
      return makeRouteDecision({
        solution: winner, agent: winner === 'orders' ? 'order-agent' : null, flow: winner === 'care' ? 'care-flow' : null, reason,
        pin: { solution: winner, expires_at: new Date(Date.now() + 24 * 3_600_000).toISOString() },
        trace: [
          { k: 'skip', t: pinned && reason !== 'pin' ? 'Pin skipped: keyword beats pin' : 'No referral tag' },
          { k: 'win', t: reason === 'pin' ? `Pin kept the chat with ${winner}` : `Keyword matched ${winner}` },
        ],
      });
    };
    const calls = await setup(page, {
      overviews: { orders: makeSolutionOverview() },
      entries: { orders: [makeEntryPoint(), makeEntryPoint({ name: 'ep-3', match_type: 'Ad or link tag', match_values: ['weekend_special'] })] },
      handlers: { simulate_route: ({ parsed }) => decide(parsed.request) },
    });
    await goto(page, '/solutions/orders?tab=test');
    await expect(page.getByText('No pin yet.')).toBeVisible();

    await page.getByRole('button', { name: 'order', exact: true }).click();
    await expect(page.getByText('Routed to Order desk')).toBeVisible();
    await expect(page.getByText('Order desk · order-agent')).toBeVisible();
    await expect(page.getByText('24h left')).toBeVisible();
    await expect(page.getByLabel('Routing trace')).toContainText('Keyword matched orders');
    let sim = callsOf(calls, 'simulate_route');
    expect(sim[0].parsed.request).toMatchObject({ gateway: 'GW-1', text: 'order', state: {}, keyword_beats_pin: false });

    // With the pin, the other solution's keyword loses...
    await page.getByLabel('Message', { exact: true }).fill('help');
    await page.getByRole('button', { name: 'Send' }).click();
    await expect(page.getByLabel('Routing trace')).toContainText('Pin kept the chat with orders');
    sim = callsOf(calls, 'simulate_route');
    expect(sim[1].parsed.request).toMatchObject({ text: 'help', state: { pin: { solution: 'orders', hours_left: 24 } }, keyword_beats_pin: false });

    // ...and wins once the toggle is flipped.
    await page.getByLabel('Keyword beats the pin (flip to compare)').check();
    await page.getByLabel('Message', { exact: true }).fill('help');
    await page.getByRole('button', { name: 'Send' }).click();
    await expect(page.getByText('Routed to Care desk')).toBeVisible();
    sim = callsOf(calls, 'simulate_route');
    expect(sim[2].parsed.request.keyword_beats_pin).toBe(true);

    // Tapping an ad chip sends the tag, not text.
    await page.getByRole('button', { name: 'Tap ad weekend_special' }).click();
    await expect.poll(() => callsOf(calls, 'simulate_route').length).toBe(4);
    expect(callsOf(calls, 'simulate_route')[3].parsed.request).toMatchObject({ ref: 'weekend_special', text: '' });

    // Hand off rewrites the pin locally and sends nothing to the server.
    await page.getByLabel('Hand off to').selectOption({ label: 'Order desk' });
    await page.getByRole('button', { name: 'Hand off', exact: true }).click();
    await expect(page.getByText('Handed off from Care desk to Order desk')).toBeVisible();
    expect(callsOf(calls, 'simulate_route').length).toBe(4);

    // Clearing the chat drops the pin.
    await page.getByRole('button', { name: 'Clear chat' }).click();
    await expect(page.getByText('No pin yet.')).toBeVisible();
  });

  test('test chat: a simulate error shows inline', async ({ page }) => {
    await setup(page, {
      overviews: { orders: makeSolutionOverview() },
      handlers: { simulate_route: () => solutionsError('invalid_payload', 'Unknown number.') },
    });
    await goto(page, '/solutions/orders?tab=test');
    await page.getByRole('button', { name: 'Hi', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Unknown number.');
  });

  test('go live, pause and resume call the API and refresh the status', async ({ page }) => {
    const overviews = { orders: makeSolutionOverview({ test_mode: true, status: 'Paused' }) };
    const calls = await setup(page, {
      overviews,
      handlers: {
        go_live: () => { overviews.orders = makeSolutionOverview({ test_mode: false, status: 'Live' }); return makeSolutionSummary(); },
        pause_solution: () => { overviews.orders = makeSolutionOverview({ status: 'Paused' }); return makeSolutionSummary({ status: 'Paused' }); },
        resume_solution: () => { overviews.orders = makeSolutionOverview({ status: 'Live' }); return makeSolutionSummary(); },
      },
    });
    await goto(page, '/solutions/orders');
    const main = page.getByRole('tabpanel');
    await expect(main.getByText('Test mode')).toBeVisible();
    await main.getByRole('button', { name: 'Go live' }).click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toContainText('Go live with Order desk?');
    await dialog.getByRole('button', { name: 'Not yet' }).click();
    expect(callsOf(calls, 'go_live')).toHaveLength(0);
    await main.getByRole('button', { name: 'Go live' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Go live' }).click();
    await expect.poll(() => callsOf(calls, 'go_live').map((c) => c.args.name)).toEqual(['orders']);

    await expect(main.getByRole('button', { name: 'Pause' })).toBeVisible();
    await expect(main.getByText('Test mode')).toHaveCount(0);
    await main.getByRole('button', { name: 'Pause' }).click();
    await expect.poll(() => callsOf(calls, 'pause_solution').map((c) => c.args.name)).toEqual(['orders']);

    await expect(main.getByRole('button', { name: 'Resume' })).toBeVisible();
    await main.getByRole('button', { name: 'Resume' }).click();
    await expect.poll(() => callsOf(calls, 'resume_solution').map((c) => c.args.name)).toEqual(['orders']);
    await expect(main.getByRole('button', { name: 'Pause' })).toBeVisible();
  });

  test('a solution without a target asks what answers and saves the choice', async ({ page }) => {
    const calls = await setup(page, {
      overviews: { orders: makeSolutionOverview({ primary: null, status: 'Paused' }) },
    });
    await goto(page, '/solutions/orders');
    await expect(page.getByText('No agent or flow answers yet')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Pause' })).toHaveCount(0);
    await page.getByLabel('Answered by').selectOption({ label: 'Order agent (agent)' });
    await page.getByRole('button', { name: 'Save' }).click();
    await expect.poll(() => callsOf(calls, 'update_solution').length).toBe(1);
    expect(callsOf(calls, 'update_solution')[0].args.name).toBe('orders');
    expect(callsOf(calls, 'update_solution')[0].parsed.fields).toEqual({ primary_target_type: 'Agent', primary_agent: 'order-agent' });
  });
});
