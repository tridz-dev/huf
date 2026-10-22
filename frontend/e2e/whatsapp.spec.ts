import { test, expect, Page } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

/**
 * WhatsApp console (/whatsapp) against a fully mocked backend: no Frappe, no Meta.
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

interface Recorded { method: string; args: Record<string, unknown> }

function body(request: { postData(): string | null; url(): string }): Record<string, unknown> {
  const data = request.postData();
  if (data) {
    try { return JSON.parse(data); } catch { return Object.fromEntries(new URLSearchParams(data)); }
  }
  return Object.fromEntries(new URL(request.url()).searchParams);
}

async function mockWhatsApp(page: Page, opts: { connector?: boolean; access?: Record<string, unknown>[] } = {}) {
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
      ? { success: true, connector_available: connector, accounts: [], gateway: gateway(String(args.gateway_name)) }
      : {
          success: true, connector_available: connector,
          gateways: [{ name: 'GW-1', health: 'healthy', enabled: true }, { name: 'GW-2', health: 'blocked', enabled: true }],
        },
  );
  await handle('check_token', () => ({
    success: true, valid: true, token_type: 'SYSTEM_USER', expires_at: null, missing_scopes: [], waba_ids: [],
    phone: { quality: 'GREEN' }, webhook_subscribed: true, checked_at: new Date().toISOString(), source: 'debug_token',
  }));
  await handle('list_message_log_filters', () => ({ success: true, statuses: [], agents: [], templates: [] }));
  await handle('list_message_log', (args) => ({
    success: true,
    items: args.gateway_name === 'GW-2' ? [logItem('g2', { gateway: 'GW-2' })] : [logItem('m1'), logItem('m2', { direction: 'out', status: 'failed', error: 'error 131047: Re-engagement message', sent_by: 'agent' })],
    next_cursor: null,
    has_more: false,
  }));
  await handle('list_templates', () => ({ success: true, templates: [] }));
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

test.describe('WhatsApp console', () => {
  test.beforeEach(async ({ page }) => {
    await mockOfflineApis(page);
  });

  test('overview shows the gateway health and writes the gateway into the URL', async ({ page }) => {
    await mockWhatsApp(page);
    await goto(page, '/whatsapp');
    await waitForContent(page);
    await expect(page.getByRole('heading', { name: 'Manage WhatsApp' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Overview' })).toHaveAttribute('data-state', 'active');
    await expect(page.getByText(/steps? left/)).toBeVisible();
    await expect(page).toHaveURL(/gateway=GW-1/);
    for (const name of ['Messages', 'Templates', 'Access', 'Settings']) {
      await expect(page.getByRole('tab', { name })).toBeVisible();
    }
  });

  test('Check now runs the token check and shows the result', async ({ page }) => {
    const calls = await mockWhatsApp(page);
    await goto(page, '/whatsapp?gateway=GW-1');
    await page.getByRole('button', { name: 'Check now' }).click();
    await expect(page.getByText('Valid', { exact: true })).toBeVisible();
    expect(calls.filter((c) => c.method === 'check_token').map((c) => c.args.gateway_name)).toEqual(['GW-1']);
  });

  test('messages tab lists the log of the chosen gateway and opens a detail sheet', async ({ page }) => {
    const calls = await mockWhatsApp(page);
    await goto(page, '/whatsapp?tab=messages&gateway=GW-1');
    await expect(page.getByText('hello m1')).toBeVisible();
    expect(calls.some((c) => c.method === 'list_message_log' && c.args.gateway_name === 'GW-1')).toBe(true);
    await page.getByText('hello m1').click();
    const sheet = page.getByRole('dialog');
    await expect(sheet.getByText('Message received')).toBeVisible();
    await expect(sheet.getByText('wamid.m1')).toBeVisible();
  });

  test('a failed message explains the Meta error in plain words', async ({ page }) => {
    await mockWhatsApp(page);
    await goto(page, '/whatsapp?tab=messages&gateway=GW-1');
    await page.getByText('hello m2').click();
    const alert = page.getByRole('dialog').getByRole('alert');
    await expect(alert).toContainText('Window closed');
    await expect(alert).toContainText('Send an approved template instead');
  });

  test('switching gateway reloads the log for the other gateway only', async ({ page }) => {
    const calls = await mockWhatsApp(page);
    await goto(page, '/whatsapp?tab=messages&gateway=GW-2');
    await expect(page.getByText('hello g2')).toBeVisible();
    await expect(page.getByText('hello m1')).toHaveCount(0);
    expect(calls.filter((c) => c.method === 'list_message_log').every((c) => c.args.gateway_name === 'GW-2')).toBe(true);
  });

  test('the send panel posts a text message from the chosen gateway', async ({ page }) => {
    const calls = await mockWhatsApp(page);
    await goto(page, '/whatsapp?tab=messages&gateway=GW-1&send=1');
    await page.getByLabel('Recipient number').fill('+15551234567');
    await page.getByLabel('Message text').fill('hi from the console');
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    await expect.poll(() => calls.find((c) => c.method === 'send_text_message')?.args).toMatchObject({
      gateway_name: 'GW-1', to: '+15551234567', text: 'hi from the console',
    });
  });

  test('access tab approves a waiting sender', async ({ page }) => {
    const calls = await mockWhatsApp(page, { access: pending });
    await goto(page, '/whatsapp?tab=access&gateway=GW-1');
    await expect(page.getByText('15551234567')).toBeVisible();
    await expect(page.getByText('PAIR-ABCD2345')).toBeVisible();
    await page.getByRole('button', { name: 'Approve' }).click();
    await expect(page.getByText('No one is waiting for approval.')).toBeVisible();
    expect(calls.find((c) => c.method === 'approve_gateway_pairing')?.args).toMatchObject({ code_or_entry_name: 'GAE-1' });
  });

  test('access tab declines a waiting sender', async ({ page }) => {
    const calls = await mockWhatsApp(page, { access: pending });
    await goto(page, '/whatsapp?tab=access&gateway=GW-1');
    await page.getByRole('button', { name: 'Decline' }).click();
    await expect(page.getByText('No one is waiting for approval.')).toBeVisible();
    expect(calls.find((c) => c.method === 'revoke_gateway_access_entry')?.args).toMatchObject({ entry_name: 'GAE-1' });
  });

  test('without the connector the templates tab explains what is missing', async ({ page }) => {
    await mockWhatsApp(page, { connector: false });
    await goto(page, '/whatsapp?tab=templates&gateway=GW-1');
    await expect(page.getByText('WhatsApp Business connector not installed')).toBeVisible();
  });

  test('a failing status call shows an error with Retry', async ({ page }) => {
    await mockWhatsApp(page);
    let first = true;
    await page.route(`${MGMT}get_setup_status{,?*}`, (route) => {
      if (first) {
        first = false;
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ message: { success: false, error: 'boom', message: 'Status is down' } }) });
      }
      return route.fallback();
    });
    await goto(page, '/whatsapp');
    await expect(page.getByText('Status is down')).toBeVisible();
    await page.getByRole('button', { name: 'Retry' }).click();
    await expect(page.getByRole('tab', { name: 'Messages' })).toBeVisible();
  });
});
