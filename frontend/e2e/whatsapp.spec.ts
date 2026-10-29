import { test, expect, Page } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';
import { callsOf, makeNumberSummary, makeSolutionSummary, mockSolutionsApi } from './helpers/solutionsMocks';

/**
 * Channels app (/channels/whatsapp) against a fully mocked backend: no Frappe, no Meta.
 * Every call under huf.ai.whatsapp.management / huf.ai.gateway_service is answered here, and the
 * requests the UI makes are recorded so the specs can assert what would have been sent.
 */

const MGMT = '**/api/method/huf.ai.whatsapp.management.';
const SERVICE = '**/api/method/huf.ai.gateway_service.';

const gateway = (name: string, over: Record<string, unknown> = {}) => ({
  name,
  enabled: true,
  whatsapp_account: `Acct-${name}`,
  phone_number_id: '123',
  account_phone_mismatch: false,
  webhook_url: `https://example.test/hook?gateway_name=${name}`,
  health: 'healthy',
  setup_stage: 'live',
  reasons: [],
  next_step: null,
  checklist: [{ code: 'credentials', state: 'done' }, { code: 'test_message', state: 'todo', action_url: '#test-message' }],
  fallback_template: null,
  fallback_template_language: null,
  fallback_template_approved: null,
  last_event_at: new Date(Date.now() - 60_000).toISOString(),
  last_error: null,
  access_token_present: true,
  app_id_present: true,
  app_secret_present: true,
  verify_token_present: true,
  events_24h: { received: 3, failed: 0, unrouted: 0, rejected: 0 },
  last_failed_event: null,
  unrouted_phone_ids: [],
  policy: {},
  meta_links: { app_dashboard: null, whatsapp_manager: null, webhook_config: null },
  ...over,
});

const logItem = (name: string, over: Record<string, unknown> = {}) => ({
  name, message_id: `wamid.${name}`, direction: 'in', phone: '+15551234567', profile_name: 'Ann', content_type: 'text',
  text: `hello ${name}`, status: 'received', error: null, template: null, creation: '2026-10-21 10:00:00', gateway: 'GW-1',
  agent: null, agent_run: null, event: null, sent_by: 'customer', ...over,
});

const templateDetail = (name: string) => ({
  name, template_id: '1', template_name: name.replace(/^tpl-/, ''), language_code: 'en_US', category: 'UTILITY', correct_category: 'UTILITY',
  category_change_pending: false, status: 'APPROVED',
  components: { header: null, body: { text: 'Order {{1}} is ready', sample_values: ['A1'] }, footer: null, buttons: [] },
  state: { rejected_reason: '', rejection_recommendation: '', other_info: '', quality_score: 'GREEN', last_event: '', last_event_at: null, last_meta_update: null },
  editable: true, edits_left: 3, manager_url: '', business_id: '',
});

interface Recorded { method: string; args: Record<string, unknown> }

function body(request: { postData(): string | null; url(): string }): Record<string, unknown> {
  const data = request.postData();
  if (data) {
    try { return JSON.parse(data); } catch { return Object.fromEntries(new URLSearchParams(data)); }
  }
  return Object.fromEntries(new URL(request.url()).searchParams);
}

interface WhatsAppMockOptions {
  connector?: boolean;
  access?: Record<string, unknown>[];
  /** Gateway fields to override on the status call (e.g. health, reasons). */
  gatewayOver?: Record<string, unknown>;
  /** Rows for list_templates, and the get_template detail used for every row. */
  templates?: Record<string, unknown>[];
  templateDetail?: Record<string, unknown>;
  /** Extra filter options for the Messages tab (Solutions support). */
  logFilters?: Record<string, unknown>;
  logItems?: Record<string, unknown>[];
}

async function mockWhatsApp(page: Page, opts: WhatsAppMockOptions = {}) {
  const calls: Recorded[] = [];
  const connector = opts.connector ?? true;
  let waiting = opts.access ?? [];
  const ok = (message: unknown) => ({ contentType: 'application/json', body: JSON.stringify({ message }) });
  const handle = (method: string, answer: (args: Record<string, unknown>) => unknown, base = MGMT) =>
    page.route(`${base}${method}{,?*}`, (route) => {
      const args = body(route.request());
      calls.push({ method, args });
      return route.fulfill(ok(answer(args)));
    });

  await handle('get_setup_status', (args) =>
    args.gateway_name
      ? { success: true, connector_available: connector, accounts: [], gateway: gateway(String(args.gateway_name), opts.gatewayOver) }
      : {
          success: true, connector_available: connector,
          gateways: [{ name: 'GW-1', health: 'healthy', enabled: true }, { name: 'GW-2', health: 'blocked', enabled: true }],
        },
  );
  await handle('check_token', () => ({
    success: true, valid: true, token_type: 'SYSTEM_USER', expires_at: null, missing_scopes: [], waba_ids: [],
    phone: { quality: 'GREEN' }, webhook_subscribed: true, checked_at: new Date().toISOString(), source: 'debug_token',
  }));
  await handle('list_message_log_filters', () => ({ success: true, statuses: [], agents: [], templates: [], ...opts.logFilters }));
  await handle('list_message_log', (args) => ({
    success: true,
    items: opts.logItems ? opts.logItems : args.gateway_name === 'GW-2' ? [logItem('g2', { gateway: 'GW-2' })] : [logItem('m1'), logItem('m2', { direction: 'out', status: 'failed', error: 'error 131047: Re-engagement message', sent_by: 'agent' })],
    next_cursor: null,
    has_more: false,
  }));
  await handle('list_templates', () => ({ success: true, templates: opts.templates ?? [] }));
  await handle('list_template_drafts', () => ({ success: true, drafts: [] }));
  await handle('get_template', (args) => ({ success: true, ...templateDetail(String(args.name)), ...opts.templateDetail }));
  await handle('send_text_message', () => ({ success: true, message_id: 'wamid.NEW' }));
  await handle('approve_gateway_pairing', () => {
    waiting = [];
    return { name: 'GAE-1', state: 'Approved', notification_status: 'sent' };
  }, SERVICE);
  await handle('revoke_gateway_access_entry', () => {
    waiting = [];
    return { name: 'GAE-1', state: 'Revoked' };
  }, SERVICE);
  await handle('list_gateway_access_entries', (args) => (args.state === 'Pending' ? waiting : []), SERVICE);
  return calls;
}

const pending = [{
  name: 'GAE-1', gateway: 'GW-1', provider: 'WhatsApp', entry_type: 'Sender', external_id: '15551234567',
  pairing_code: 'PAIR-ABCD2345', state: 'Pending', creation: '2026-10-21 10:00:00',
}];

test.describe('Channels: WhatsApp', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
    // The page also reads per-number Solutions data; answer it with an empty, harmless summary.
    await mockSolutionsApi(page);
  });

  test('/channels/whatsapp resolves to the first number Home and shows its health', async ({ page }) => {
    await mockWhatsApp(page);
    await goto(page, '/channels/whatsapp');
    await waitForContent(page);
    await expect(page).toHaveURL(/\/channels\/whatsapp\/n\/GW-1\/home/);
    await expect(page.getByRole('heading', { name: 'Home', level: 1 })).toBeVisible();
    await expect(page.getByText('Needs attention', { exact: true })).toBeVisible();
    const rail = page.getByRole('navigation', { name: 'Channels' });
    for (const name of ['Home', 'Activity', 'Broadcasts', 'Templates', 'Automations', 'Connections', 'Numbers', 'Settings']) {
      await expect(rail.getByRole('link', { name })).toBeVisible();
    }
  });

  test('the legacy /whatsapp URL redirects into the Channels app', async ({ page }) => {
    await mockWhatsApp(page);
    await goto(page, ['/whatsapp', 'tab=messages&gateway=GW-2'].join('?'));
    await expect(page).toHaveURL(/\/channels\/whatsapp\/n\/GW-2\/home/);
  });

  test('Check now runs the token check and shows the result', async ({ page }) => {
    const calls = await mockWhatsApp(page);
    await goto(page, '/channels/whatsapp/n/GW-1/home');
    await page.getByRole('button', { name: 'Check now' }).click();
    await expect(page.getByText('Valid', { exact: true })).toBeVisible();
    expect(calls.filter((c) => c.method === 'check_token').map((c) => c.args.gateway_name)).toEqual(['GW-1']);
  });

  test('activity lists the log of the chosen gateway and opens a detail sheet', async ({ page }) => {
    const calls = await mockWhatsApp(page);
    await goto(page, '/channels/whatsapp/n/GW-1/activity');
    await expect(page.getByText('hello m1')).toBeVisible();
    expect(calls.some((c) => c.method === 'list_message_log' && c.args.gateway_name === 'GW-1')).toBe(true);
    await page.getByText('hello m1').click();
    const sheet = page.getByRole('dialog');
    await expect(sheet.getByText('Message received')).toBeVisible();
    await expect(sheet.getByText('wamid.m1')).toBeVisible();
  });

  test('a failed message explains the Meta error in plain words', async ({ page }) => {
    await mockWhatsApp(page);
    await goto(page, '/channels/whatsapp/n/GW-1/activity');
    await page.getByText('hello m2').click();
    const alert = page.getByRole('dialog').getByRole('alert');
    await expect(alert).toContainText('Window closed');
    await expect(alert).toContainText('Send an approved template instead');
  });

  test('switching gateway reloads the log for the other gateway only', async ({ page }) => {
    const calls = await mockWhatsApp(page);
    await goto(page, '/channels/whatsapp/n/GW-2/activity');
    await expect(page.getByText('hello g2')).toBeVisible();
    await expect(page.getByText('hello m1')).toHaveCount(0);
    expect(calls.filter((c) => c.method === 'list_message_log').every((c) => c.args.gateway_name === 'GW-2')).toBe(true);
  });

  test('activity is read-only: no send panel, even with the legacy ?send=1', async ({ page }) => {
    const calls = await mockWhatsApp(page);
    await goto(page, '/channels/whatsapp/n/GW-1/activity?send=1');
    await expect(page.getByText('hello m1')).toBeVisible();
    await expect(page.getByLabel('Message text')).toHaveCount(0);
    expect(calls.some((c) => c.method === 'send_text_message')).toBe(false);
  });

  test('settings > access approves a waiting sender', async ({ page }) => {
    const calls = await mockWhatsApp(page, { access: pending });
    await goto(page, '/channels/whatsapp/n/GW-1/settings/access');
    await expect(page.getByText('15551234567')).toBeVisible();
    await expect(page.getByText('PAIR-ABCD2345')).toBeVisible();
    await page.getByRole('button', { name: 'Approve' }).click();
    await expect(page.getByText('No one is waiting for approval.')).toBeVisible();
    expect(calls.find((c) => c.method === 'approve_gateway_pairing')?.args).toMatchObject({ code_or_entry_name: 'GAE-1' });
  });

  test('settings > access declines a waiting sender', async ({ page }) => {
    const calls = await mockWhatsApp(page, { access: pending });
    await goto(page, '/channels/whatsapp/n/GW-1/settings/access');
    await page.getByRole('button', { name: 'Decline' }).click();
    await expect(page.getByText('No one is waiting for approval.')).toBeVisible();
    expect(calls.find((c) => c.method === 'revoke_gateway_access_entry')?.args).toMatchObject({ entry_name: 'GAE-1' });
  });

  test('without the connector Templates explains what is missing', async ({ page }) => {
    await mockWhatsApp(page, { connector: false });
    await goto(page, '/channels/whatsapp/n/GW-1/templates');
    await expect(page.getByText('WhatsApp Business connector not installed')).toBeVisible();
  });

  test('a failing status call shows an error on Home, and a reload recovers', async ({ page }) => {
    await mockWhatsApp(page);
    let failing = true;
    await page.route(`${MGMT}get_setup_status{,?*}`, (route) => {
      // Only the per-number call fails; the site summary behind the rail keeps working.
      if (failing && body(route.request()).gateway_name) {
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ message: { success: false, error: 'boom', message: 'Status is down' } }) });
      }
      return route.fallback();
    });
    await goto(page, '/channels/whatsapp/n/GW-1/home');
    await expect(page.getByText('Status is down').first()).toBeVisible();
    failing = false;
    await page.reload();
    await expect(page.getByText('Needs attention', { exact: true })).toBeVisible();
  });
});

// --- Solutions inside the Channels app ------------------------------------------------------------

const orders = makeSolutionSummary();
const care = makeSolutionSummary({ name: 'care', title: 'Care desk', purpose: 'support' });

const busyNumber = (over: Record<string, unknown> = {}) =>
  makeNumberSummary({
    solutions: [
      { name: 'orders', title: 'Order desk', status: 'Live', usage_pct: 42.4, sends_24h: 420 },
      { name: 'care', title: 'Care desk', status: 'Paused', usage_pct: null, sends_24h: 0 },
    ],
    routing_order: [
      { rank: 1, kind: 'keyword', label: 'Keyword: order', solution: 'orders' },
      { rank: 2, kind: 'keyword', label: 'Keyword: help', solution: 'care' },
      { rank: 3, kind: 'triage', label: 'Anything else', solution: '' },
    ],
    ...over,
  });

const sharedRow = {
  name: 'tpl-order_ready_pickup', template_name: 'order_ready_pickup', category: 'UTILITY', language_code: 'en_US', status: 'APPROVED',
  template: 'Your order is ready', shared: true, used_by: [{ solution: 'orders', title: 'Order desk' }, { solution: 'care', title: 'Care desk' }],
  owner: { solution: 'orders', title: 'Order desk' },
};
const ownRow = {
  name: 'tpl-weekend_special', template_name: 'weekend_special', category: 'MARKETING', language_code: 'en_US', status: 'APPROVED',
  template: 'Weekend treats', shared: false, used_by: [{ solution: 'orders', title: 'Order desk' }], owner: { solution: 'orders', title: 'Order desk' },
};
const unusedRow = {
  name: 'tpl-unused_one', template_name: 'unused_one', category: 'UTILITY', language_code: 'en_US', status: 'APPROVED',
  template: 'Nobody uses me', shared: false, used_by: [], owner: null,
};

test.describe('Channels: WhatsApp with Solutions', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('the rail number picker lists every number and switches to its Home', async ({ page }) => {
    await mockWhatsApp(page);
    await mockSolutionsApi(page);
    await goto(page, '/channels/whatsapp/n/GW-1/home');
    const picker = page.getByRole('combobox', { name: 'Number' });
    await expect(picker.getByRole('option', { name: 'GW-1' })).toHaveCount(1);
    await expect(picker.getByRole('option', { name: 'GW-2' })).toHaveCount(1);
    await picker.selectOption('GW-2');
    await expect(page).toHaveURL(/\/channels\/whatsapp\/n\/GW-2\/home/);
  });

  test('overview lists the solutions on the number and the routing order', async ({ page }) => {
    await mockWhatsApp(page);
    const calls = await mockSolutionsApi(page, { numberSummaries: { 'GW-1': busyNumber() } });
    await goto(page, '/channels/whatsapp/n/GW-1/automations/agents');
    await expect.poll(() => callsOf(calls, 'get_number_summary').map((c) => c.args.gateway)).toContain('GW-1');

    await expect(page.getByText('Solutions on this number', { exact: true })).toBeVisible();
    const orderRow = page.getByRole('listitem').filter({ hasText: 'Order desk' });
    const careRow = page.getByRole('listitem').filter({ hasText: 'Care desk' });
    await expect(orderRow).toContainText('Live');
    await expect(orderRow.getByRole('meter', { name: 'Order desk daily limit used' })).toHaveAttribute('aria-valuenow', '42');
    await expect(orderRow).toContainText('42%');
    await expect(careRow).toContainText('Paused');
    await expect(careRow).toContainText('n/a');
    await expect(page.getByText('2 solutions share this number')).toBeVisible();
    await expect(page.getByRole('link', { name: /Add solution/ })).toHaveAttribute('href', /\/solutions\/new\?gateway=GW-1/);
    await expect(orderRow.getByRole('link', { name: /Open\s*Order desk/ })).toHaveAttribute('href', /\/solutions\/orders$/);

    await expect(page.getByText('Routing order', { exact: true })).toBeVisible();
    const rows = page.getByRole('row');
    await expect(rows.filter({ hasText: 'Keyword: order' })).toContainText('Order desk');
    await expect(rows.filter({ hasText: 'Keyword: help' })).toContainText('Care desk');
    await expect(rows.filter({ hasText: 'Keyword: help' })).toContainText('Paused');
    await expect(rows.filter({ hasText: 'Anything else' })).toContainText('Triage assistant');
  });

  test('a number with no live solution says it replies to no one', async ({ page }) => {
    await mockWhatsApp(page);
    await mockSolutionsApi(page, { numberSummaries: { 'GW-1': busyNumber({ solutions: [{ name: 'care', title: 'Care desk', status: 'Paused', usage_pct: null, sends_24h: 0 }], routing_order: [] }) } });
    await goto(page, '/channels/whatsapp/n/GW-1/automations/agents');
    await expect(page.getByText('This number replies to no one yet.')).toBeVisible();
    await expect(page.getByText('No rules')).toBeVisible();
  });

  test('a degraded number blames the solution that sent the most', async ({ page }) => {
    await mockWhatsApp(page, {
      gatewayOver: { health: 'degraded', reasons: [{ code: 'delivery_failures', message: 'Meta is rejecting some messages.' }] },
    });
    await mockSolutionsApi(page, {
      numberSummaries: { 'GW-1': busyNumber({ quality: { rating: 'Medium', source: 'meta' }, blame: { solution: 'orders', share_pct: 91 } }) },
    });
    await goto(page, '/channels/whatsapp/n/GW-1/home');
    const banner = page.getByRole('alert').filter({ hasText: 'Meta is rejecting some messages.' });
    await expect(banner).toContainText('Quality is medium.');
    await expect(banner).toContainText("Most of today's sends came from Order desk (91% of sends in the last 24 hours).");
    await expect(banner.getByRole('link', { name: 'Order desk' })).toHaveAttribute('href', /\/solutions\/orders$/);
  });

  test('no blame line while the number is healthy and quality is good', async ({ page }) => {
    await mockWhatsApp(page);
    await mockSolutionsApi(page, {
      numberSummaries: { 'GW-1': busyNumber({ quality: { rating: 'High', source: 'meta' }, blame: { solution: 'orders', share_pct: 91 } }) },
    });
    await goto(page, '/channels/whatsapp/n/GW-1/home');
    await expect(page.getByLabel('Counters')).toBeVisible();
    await expect(page.getByText(/Most of today's sends/)).toHaveCount(0);
  });

  test('a failing Solutions summary hides its cards and nothing else', async ({ page }) => {
    await mockWhatsApp(page);
    await mockSolutionsApi(page, {
      handlers: { get_number_summary: () => ({ error: { code: 'not_permitted', message: 'No.' } }) },
    });
    await goto(page, '/channels/whatsapp/n/GW-1/automations/agents');
    await expect(page.getByRole('navigation', { name: 'Automation tabs' })).toBeVisible();
    await expect(page.getByText('Solutions on this number', { exact: true })).toHaveCount(0);
    await expect(page.getByText('Routing order', { exact: true })).toHaveCount(0);
  });

  test('templates: Any solution filter, Used by chips and the Shared pill', async ({ page }) => {
    await mockWhatsApp(page, { templates: [sharedRow, ownRow, unusedRow] });
    await mockSolutionsApi(page, { solutions: [orders, care] });
    await goto(page, '/channels/whatsapp/n/GW-1/templates');
    const list = page.getByRole('list').filter({ hasText: 'order_ready_pickup' });
    await expect(list.getByRole('listitem')).toHaveCount(3);
    const shared = list.getByRole('listitem').filter({ hasText: 'order_ready_pickup' });
    await expect(shared.getByText('Shared', { exact: true })).toBeVisible();
    await expect(shared.getByTestId('used-by')).toContainText('Order desk');
    await expect(shared.getByTestId('used-by')).toContainText('Care desk');
    await expect(list.getByRole('listitem').filter({ hasText: 'weekend_special' }).getByText('Shared', { exact: true })).toHaveCount(0);
    await expect(list.getByRole('listitem').filter({ hasText: 'unused_one' }).getByTestId('used-by')).toHaveCount(0);

    const filter = page.getByRole('combobox', { name: 'Filter by solution' });
    await expect(filter).toContainText('Any solution');
    await filter.click();
    await page.getByRole('option', { name: 'Care desk' }).click();
    await expect(list.getByRole('listitem')).toHaveCount(1);
    await expect(list).toContainText('order_ready_pickup');
    await filter.click();
    await page.getByRole('option', { name: 'Order desk' }).click();
    await expect(list.getByRole('listitem')).toHaveCount(2);
    await expect(list).not.toContainText('unused_one');
  });

  test('editing a shared template asks first: Cancel, Make a copy, Edit for everyone', async ({ page }) => {
    await mockWhatsApp(page, { templates: [sharedRow, ownRow] });
    await mockSolutionsApi(page, { solutions: [orders, care] });
    await goto(page, '/channels/whatsapp/n/GW-1/templates');
    const edit = page.getByRole('button', { name: 'Edit and resubmit' });
    await edit.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('This template is shared');
    await expect(dialog).toContainText('Used by Order desk and Care desk.');
    await expect(dialog).toContainText('Editing resubmits it to Meta for all of them');
    for (const name of ['Edit for everyone', 'Make a copy', 'Cancel']) await expect(dialog.getByRole('button', { name })).toBeVisible();

    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page).not.toHaveURL(/edit=|new=1/);

    await edit.click();
    await page.getByRole('dialog').getByRole('button', { name: 'Make a copy' }).click();
    await expect(page).toHaveURL(/new=1/);
    await expect(page.getByRole('dialog')).toHaveCount(0);

    await goto(page, '/channels/whatsapp/n/GW-1/templates');
    await page.getByRole('button', { name: 'Edit and resubmit' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Edit for everyone' }).click();
    await expect(page).toHaveURL(/edit=tpl-order_ready_pickup/);
  });

  test('editing a template used by one solution needs no warning', async ({ page }) => {
    await mockWhatsApp(page, { templates: [ownRow] });
    await mockSolutionsApi(page, { solutions: [orders, care] });
    await goto(page, '/channels/whatsapp/n/GW-1/templates');
    await page.getByRole('button', { name: 'Edit and resubmit' }).click();
    await expect(page).toHaveURL(/edit=tpl-weekend_special/);
    await expect(page.getByText('This template is shared')).toHaveCount(0);
  });

  test('messages: Solution column and filter', async ({ page }) => {
    const calls = await mockWhatsApp(page, {
      logFilters: { solutions: [{ name: 'orders', title: 'Order desk' }, { name: 'care', title: 'Care desk' }] },
      logItems: [
        logItem('m1', { solution: { name: 'orders', title: 'Order desk' } }),
        logItem('m2', { direction: 'out', sent_by: 'agent', solution: null }),
      ],
    });
    await mockSolutionsApi(page);
    await goto(page, '/channels/whatsapp/n/GW-1/activity');
    await expect(page.getByRole('columnheader', { name: 'Solution' })).toBeVisible();
    const m1 = page.getByRole('row').filter({ hasText: 'hello m1' });
    const m2 = page.getByRole('row').filter({ hasText: 'hello m2' });
    await expect(m1).toContainText('Order desk');
    await expect(m2).not.toContainText('Order desk');

    const filter = page.getByRole('combobox', { name: 'Solution' });
    await expect(filter).toContainText('Any solution');
    await filter.click();
    await page.getByRole('option', { name: 'Care desk' }).click();
    await expect.poll(() => calls.filter((c) => c.method === 'list_message_log').map((c) => c.args.solution)).toContain('care');
    await expect(page).toHaveURL(/solution=care/);
  });

  test('messages: servers without Solutions support show no Solution column or filter', async ({ page }) => {
    await mockWhatsApp(page);
    await mockSolutionsApi(page);
    await goto(page, '/channels/whatsapp/n/GW-1/activity');
    await expect(page.getByText('hello m1')).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Solution' })).toHaveCount(0);
    await expect(page.getByRole('combobox', { name: 'Solution' })).toHaveCount(0);
  });
});
