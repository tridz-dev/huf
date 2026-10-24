/**
 * Offline mocks + route list for the form-geometry spec (e2e/form-geometry.spec.ts).
 * Ported from the UI audit driver (RepoStructure/ongoing6/measure/audit.mjs): the same
 * canned gateways, templates, message log, integrations, and the same 33 audited screens.
 * No Frappe backend is needed; every /api/** call is answered here.
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import type { Page } from '@playwright/test';

const now = Date.now();
const iso = (m: number) => new Date(now - m * 60000).toISOString();
const ts = (m: number) => new Date(now - m * 60000).toISOString().replace('T', ' ').slice(0, 19);

const waGateway = (name: string): any => ({
  name, enabled: true, whatsapp_account: `Acct-${name}`, phone_number_id: '109876543210', account_phone_mismatch: false,
  webhook_url: `https://huf.example.test/api/method/huf.ai.whatsapp.webhook?gateway_name=${name}`,
  health: name === 'GW-2' ? 'blocked' : 'healthy', reasons: name === 'GW-2' ? ['token_expired'] : [], next_step: null,
  checklist: [{ code: 'credentials', state: 'done' }, { code: 'webhook', state: 'done' }, { code: 'test_message', state: 'todo', action_url: '#test-message' }],
  fallback_template: 'order_update', fallback_template_language: 'en_US', fallback_template_approved: true,
  last_event_at: iso(3), last_error: null, access_token_present: true, app_id_present: true, app_secret_present: true, verify_token_present: true,
  events_24h: { received: 128, failed: 2, unrouted: 1, rejected: 0 }, last_failed_event: null, unrouted_phone_ids: [],
  policy: { direct_policy: 'Pairing', room_policy: 'Disabled', pairing_ttl_minutes: 60 },
  meta_links: { app_dashboard: 'https://developers.facebook.com/apps/1', whatsapp_manager: 'https://business.facebook.com/wa/manage', webhook_config: null },
});
const STATUSES = ['APPROVED', 'PENDING', 'REJECTED', 'PAUSED', 'DISABLED', 'IN_APPEAL'];
const templates: any[] = STATUSES.map((s: string, i: number) => ({
  name: `TPL-${i + 1}`, template_name: ['order_update', 'welcome_offer', 'payment_reminder', 'shipping_delay', 'old_promo', 'otp_code'][i],
  actual_name: ['order_update', 'welcome_offer', 'payment_reminder', 'shipping_delay', 'old_promo', 'otp_code'][i],
  category: i === 5 ? 'AUTHENTICATION' : i % 2 ? 'MARKETING' : 'UTILITY', language_code: 'en_US', status: s, id: `10${i}`,
  whatsapp_account: 'Acct-GW-1', header_type: 'TEXT', header: 'Order {{1}}', footer: 'Reply STOP to opt out',
  template: 'Hi {{1}}, your order {{2}} is on its way. Track it here.', sample_values: 'Ann,#4512',
  buttons: [{ button_type: 'QUICK_REPLY', button_label: 'Track' }], rejected_reason: s === 'REJECTED' ? 'INVALID_FORMAT' : '',
  quality_score: s === 'APPROVED' ? 'GREEN' : '', last_meta_update: ts(60 * (i + 1)),
}));
const detail = (t: any) => ({
  name: t.name, template_id: t.id, template_name: t.template_name, language_code: 'en_US', category: t.category,
  correct_category: t.category, category_change_pending: false, status: t.status, whatsapp_account: 'Acct-GW-1',
  components: { header: { type: 'TEXT', text: 'Order {{1}}', sample: '#4512' }, body: { text: t.template, sample_values: ['Ann', '#4512'] },
    footer: { text: t.footer }, buttons: [{ type: 'QUICK_REPLY', text: 'Track' }, { type: 'URL', text: 'Open', url: 'https://shop.example.test/o/{{1}}', example: 'https://shop.example.test/o/4512' }] },
  state: { rejected_reason: t.rejected_reason, rejection_recommendation: t.rejected_reason ? 'Remove variables at the start of the body.' : '', other_info: '',
    quality_score: t.quality_score, last_event: 'APPROVED', last_event_at: ts(30), last_meta_update: ts(30) },
  parameter_format: 'POSITIONAL', editable: true, edits_left: 9, manager_url: 'https://business.facebook.com/wa/manage/templates', business_id: '555',
});
const drafts: any[] = [
  { name: 'DR-1', template_name: 'agent_followup', language_code: 'en_US', category: 'UTILITY', status: 'Pending Review', requested_via: 'Agent run', agent_run: 'RUN-77', requested_by: 'Support Agent', creation: ts(90),
    payload: { name: 'agent_followup', category: 'UTILITY', language: 'en_US', body: { text: 'Hi {{1}}, following up on ticket {{2}}.', examples: ['Ann', 'T-9'] } } },
  { name: 'DR-2', template_name: 'promo_fall', language_code: 'en_US', category: 'MARKETING', status: 'Failed', submit_error: 'Meta rejected: duplicate name', requested_via: 'User', creation: ts(300), payload: { name: 'promo_fall', category: 'MARKETING', language: 'en_US', body: { text: 'Fall sale!' } } },
  { name: 'DR-3', template_name: 'draft_only', language_code: 'en_US', category: 'UTILITY', status: 'Draft', requested_via: 'User', creation: ts(600), payload: { name: 'draft_only' } },
];
const logItem = (i: number, over: any = {}) => ({
  name: `ML-${i}`, message_id: `wamid.${i}`, direction: i % 2 ? 'out' : 'in', phone: `+1555123${String(4500 + i)}`, profile_name: ['Ann Lee', 'Omar K', 'Priya S', 'Diego R'][i % 4],
  content_type: i % 5 === 3 ? 'template' : 'text', text: ['Hi, where is my order?', 'It ships today.', 'Can I change the address?', 'Template: order_update'][i % 4],
  status: i === 3 ? 'failed' : i % 2 ? 'delivered' : 'received', error: i === 3 ? 'error 131047: Re-engagement message' : null, template: i % 5 === 3 ? 'order_update' : null,
  creation: ts(i * 7), gateway: 'GW-1', agent: i % 2 ? 'Support Agent' : null, agent_run: i % 2 ? `RUN-${i}` : null, event: null, sent_by: i % 2 ? 'agent' : 'customer', ...over,
});
const pending: any[] = [
  { name: 'GAE-1', gateway: 'GW-1', provider: 'WhatsApp', entry_type: 'Sender', external_id: '15551234567', display_name: 'Ann Lee', pairing_code: 'PAIR-ABCD2345', state: 'Pending', creation: ts(20) },
  { name: 'GAE-2', gateway: 'TG-Support', provider: 'Telegram', entry_type: 'Sender', external_id: '884422', display_name: '@omar', pairing_code: 'PAIR-QWER7788', state: 'Pending', creation: ts(45) },
];
const gatewaysDocs: any[] = [
  { name: 'GW-1', gateway_name: 'Support WhatsApp', provider: 'WhatsApp', is_enabled: 1, integration_settings: 'WA-Settings', direct_policy: 'Pairing', room_policy: 'Disabled', default_target_type: 'Agent', default_agent: 'Support Agent', last_event_at: ts(3) },
  { name: 'GW-2', gateway_name: 'Sales WhatsApp', provider: 'WhatsApp', is_enabled: 1, integration_settings: 'WA-Sales', direct_policy: 'Allow list', default_target_type: 'Flow', default_flow: 'Lead Intake', last_error: 'Token expired', last_event_at: ts(2000) },
  { name: 'TG-Support', gateway_name: 'Support Telegram', provider: 'Telegram', is_enabled: 1, integration_settings: 'Telegram Bot', direct_policy: 'Pairing', room_policy: 'Allow list', mention_required: 1, pairing_ttl_minutes: 30, default_target_type: 'Agent', default_agent: 'Support Agent', last_event_at: ts(15) },
  { name: 'SL-1', gateway_name: 'Team Slack', provider: 'Slack', is_enabled: 0, direct_policy: 'Disabled', description: 'Not connected yet' },
  { name: 'MS-1', gateway_name: 'Messenger page', provider: 'Messenger', is_enabled: 1, integration_settings: 'Messenger Page', direct_policy: 'Open', default_target_type: 'Agent', default_agent: 'Sales Agent' },
];
const services: Record<string, any> = {
  telegram: { name: 'telegram', service_name: 'telegram', category: 'Communication', surface: 'Gateway', description: 'Telegram bot gateway',
    required_credentials: JSON.stringify([{ key: 'bot_token', label: 'Bot token', required: true, secret: true }, { key: 'bot_username', label: 'Bot username', required: false }]) },
  whatsapp: { name: 'whatsapp', service_name: 'whatsapp', category: 'Communication', surface: 'Gateway', description: 'WhatsApp Cloud API',
    required_credentials: JSON.stringify([{ key: 'access_token', label: 'Access token', required: true, secret: true }, { key: 'phone_number_id', label: 'Phone number ID', required: true }, { key: 'app_secret', label: 'App secret', secret: true }]) },
  messenger: { name: 'messenger', service_name: 'messenger', category: 'Communication', surface: 'Gateway', required_credentials: '[]' },
  github: { name: 'github', service_name: 'github', category: 'Developer', surface: 'Integration', description: 'GitHub API', required_credentials: JSON.stringify([{ key: 'token', label: 'Token', required: true, secret: true }]) },
};
const settings: Record<string, any> = {
  'Telegram Bot': { name: 'Telegram Bot', service: 'telegram', is_active: 1, is_default: 1, credentials: [{ key: 'bot_token', value: '********', is_mandatory: 1 }, { key: 'bot_username', value: 'huf_support_bot' }],
    recipients: [{ recipient_name: 'Ops chat', recipient_id: '-100223344' }], telegram_agent: 'Support Agent', telegram_auto_setup_webhook: 1, telegram_webhook_url: 'https://huf.example.test/api/method/huf.ai.telegram.webhook', telegram_webhook_status: 'Active', telegram_last_webhook_setup: ts(500), last_used: ts(15), modified: ts(100) },
  'WA-Settings': { name: 'WA-Settings', service: 'whatsapp', is_active: 1, is_default: 1, credentials: [{ key: 'access_token', value: '********', is_mandatory: 1 }, { key: 'phone_number_id', value: '109876543210', is_mandatory: 1 }, { key: 'app_secret', value: '' }], recipients: [], modified: ts(80) },
  'WA-Sales': { name: 'WA-Sales', service: 'whatsapp', is_active: 1, is_default: 0, credentials: [], modified: ts(80), last_error: 'Token expired' },
  'Messenger Page': { name: 'Messenger Page', service: 'messenger', is_active: 1, is_default: 0, credentials: [], modified: ts(80) },
  'GitHub Main': { name: 'GitHub Main', service: 'github', is_active: 1, is_default: 1, credentials: [{ key: 'token', value: '****' }], modified: ts(80) },
};
const agents = [{ name: 'Support Agent', agent_name: 'Support Agent' }, { name: 'Sales Agent', agent_name: 'Sales Agent' }];

function args(req: any): any {
  const d = req.postData();
  if (d) { try { return JSON.parse(d); } catch { return Object.fromEntries(new URLSearchParams(d)); } }
  return Object.fromEntries(new URL(req.url()).searchParams);
}
function answer(url: string, req: any): any {
  const u = decodeURIComponent(url);
  const a = args(req);
  const m = (x: any) => ({ message: x });
  const meth = (u.match(/\/api\/method\/([^?]+)/) || [])[1] || '';
  const short = meth.split('.').pop();
  if (meth.includes('get_logged_user')) return m('Administrator');
  if (meth.includes('huf.permissions.get_me')) return m({ user: 'Administrator', full_name: 'Administrator', huf_role: 'Huf Admin', capabilities: ['agent.use','agent.view_all','flows.use','chat.use','users.manage','roles.manage','system.providers.manage','system.integrations.manage','system.mcp.manage','data.tables.manage','data.records.view_own','data.records.view_all'] });
  if (meth.includes('get_count')) return m(3);
  if (meth.includes('whatsapp.management') || meth.includes('gateway_service')) {
    const ms = (x: any) => m(x && typeof x === 'object' && !Array.isArray(x) ? { success: true, ...x } : x);
    switch (short) {
      case 'get_setup_status': return ms(a.gateway_name ? { success: true, connector_available: true, accounts: [], gateway: waGateway(String(a.gateway_name)) }
        : { success: true, connector_available: true, gateways: [{ name: 'GW-1', health: 'healthy', enabled: true }, { name: 'GW-2', health: 'blocked', enabled: true }] });
      case 'check_token': return ms({ success: true, valid: true, token_type: 'SYSTEM_USER', expires_at: null, missing_scopes: [], waba_ids: ['555'], phone: { quality: 'GREEN', display_phone_number: '+1 555 010 2000', verified_name: 'Huf Support' }, webhook_subscribed: true, checked_at: iso(1), source: 'debug_token' });
      case 'list_message_log_filters': return ms({ success: true, statuses: ['received', 'delivered', 'failed', 'read'], agents: ['Support Agent'], templates: ['order_update'] });
      case 'list_message_log': return ms({ success: true, items: Array.from({ length: 14 }, (_: unknown, i: number) => logItem(i + 1)), next_cursor: null, has_more: false });
      case 'list_templates': return ms({ success: true, templates, manager_url: 'https://business.facebook.com/wa/manage/templates', business_id: '555' });
      case 'get_template': return ms(detail(templates.find((t: any) => t.name === a.name) || templates[0]));
      case 'list_template_drafts': return ms({ drafts });
      case 'list_gateway_access_entries': return ms(a.state === 'Pending' ? pending : [{ ...pending[0], name: 'GAE-9', state: 'Approved', pairing_code: null }]);
      case 'preview_gateway_readiness': return ms({ ready: false, checks: [] });
      default: return m({ success: true });
    }
  }
  if (meth.includes('get_list') || meth.includes('get_service_tools')) return m([]);
  // resources
  const r = u.match(/\/api\/resource\/([^/?]+)(?:\/([^?]+))?/);
  if (r) {
    const [, dt, name] = r;
    if (dt === 'User') return { data: { name: 'Administrator', email: 'admin@example.com', full_name: 'Administrator' } };
    if (dt === 'Gateway') return name ? { data: gatewaysDocs.find((g: any) => g.name === name) || gatewaysDocs[0] } : { data: gatewaysDocs };
    if (dt === 'Integration Settings') {
      if (name) return { data: settings[name] || settings['Telegram Bot'] };
      return { data: Object.values(settings).map(({ credentials: _c, recipients: _r, ...s }: any) => s) };
    }
    if (dt === 'Integration Service') return name ? { data: services[name] || services.telegram } : { data: Object.values(services) };
    if (dt === 'Agent') return name ? { data: agents[0] } : { data: agents };
    if (dt === 'Flow Definition') return { data: [{ name: 'Lead Intake', title: 'Lead Intake' }] };
    if (dt === 'WhatsApp Account') return { data: [{ name: 'Acct-GW-1' }] };
    return name ? { data: {} } : { data: [] };
  }
  if (meth.includes('frappe.client.get_value')) return m({});
  if (meth.includes('get_execution_analytics')) return m({ summary: {}, series: [], breakdowns: [], metadata: {} });
  return m([]);
}

/** Install the /api/** mock on a page (or context-like with route()). */
export async function mockFormGeometryApis(page: Page) {
  await page.route('**/api/**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(answer(route.request().url(), route.request())) }),
  );
  await page.route('**/huf/stream/ping', (r) => r.fulfill({ contentType: 'application/json', body: '{"ok":true}' }));
  await page.route('**/socket.io/**', (r) => r.abort());
}

// ---- screens --------------------------------------------------------------
// Falls back to a dispatched click when another element intercepts the pointer (seen with the
// template detail pane's Send button at 1024px); the geometry run only needs the dialog opened.
const click = async (page: Page, sel: string, opts: any = {}) => {
  const loc = page.locator(sel).first();
  try {
    await loc.click({ timeout: 4000, ...opts });
  } catch (e) {
    if (!String((e as Error).message).includes('intercepts pointer events')) throw e;
    await loc.dispatchEvent('click');
  }
  await page.waitForTimeout(500);
};
export type GeometryRoute = { id: string; path: string; act?: (p: Page) => Promise<void> };
const S: Array<[string, string, ((p: Page) => Promise<void>)?]> = [
  ['wa-overview', 'whatsapp?gateway=GW-1'],
  ['wa-overview-blocked', 'whatsapp?gateway=GW-2'],
  ['wa-messages', 'whatsapp?tab=messages&gateway=GW-1'],
  ['wa-message-detail', 'whatsapp?tab=messages&gateway=GW-1', async (p: Page) => { await click(p, 'table tbody tr >> nth=2'); }],
  ['wa-messages-send', 'whatsapp?tab=messages&gateway=GW-1&send=1'],
  ['wa-templates', 'whatsapp?tab=templates&gateway=GW-1'],
  ['wa-template-rejected', 'whatsapp?tab=templates&gateway=GW-1', async (p: Page) => { await click(p, 'text=payment_reminder'); }],
  ['wa-template-send-dialog', 'whatsapp?tab=templates&gateway=GW-1', async (p: Page) => { await click(p, 'text=order_update'); await p.waitForTimeout(800); await click(p, 'button:has-text("Send"):not([disabled])'); }],
  ['wa-drafts', 'whatsapp?tab=templates&gateway=GW-1', async (p: Page) => { await click(p, '[role=tab]:has-text("Drafts")'); }],
  ['wa-draft-detail', 'whatsapp?tab=templates&gateway=GW-1', async (p: Page) => { await click(p, '[role=tab]:has-text("Drafts")'); await click(p, 'button:has-text("Review")'); }],
  ['wa-wizard-type', 'whatsapp?tab=templates&gateway=GW-1&new=1'],
  ['wa-wizard-write', 'whatsapp?tab=templates&gateway=GW-1&new=1', async (p: Page) => { await click(p, 'button:has-text("Next")'); }],
  ['wa-wizard-write-filled', 'whatsapp?tab=templates&gateway=GW-1&new=1', async (p: Page) => {
    await click(p, 'button:has-text("Next")');
    const ins = p.locator('main input:visible'); const n = await ins.count();
    for (let i = 0; i < Math.min(n, 3); i++) { try { await ins.nth(i).fill(i ? 'Order {{1}}' : 'order_shipped'); } catch {} }
    const ta = p.locator('main textarea:visible'); if (await ta.count()) await ta.first().fill('Hi {{1}}, order {{2}} shipped.');
    await p.waitForTimeout(400);
  }],
  ['wa-wizard-review', 'whatsapp?tab=templates&gateway=GW-1&edit=TPL-1', async (p: Page) => { await click(p, 'button:has-text("Next")'); }],
  ['wa-wizard-edit', 'whatsapp?tab=templates&gateway=GW-1&edit=TPL-1'],
  ['wa-access', 'whatsapp?tab=access&gateway=GW-1'],
  ['wa-settings', 'whatsapp?tab=settings&gateway=GW-1'],
  ['gw-list', 'gateways'],
  ['gw-add-setup', 'gateways', async (p: Page) => { await click(p, 'button:has-text("Add gateway")'); }],
  ['gw-pending-access', 'gateways', async (p: Page) => { await click(p, 'button:has-text("Pending access")'); }],
  ['gw-credentials', 'gateways', async (p: Page) => { await click(p, 'button:has-text("Channel credentials")'); }],
  ['gw-edit-modal', 'gateways', async (p: Page) => {
    const card = p.locator(':text("Team Slack")').first(); await card.scrollIntoViewIfNeeded();
    const box = card.locator("xpath=ancestor::*[.//button[@title='Configure gateway' or @title='More actions']][1]").first();
    const direct = box.locator("button[title='Configure gateway']");
    if (await direct.count()) await direct.first().click(); else { await box.locator("button[title='More actions']").first().click(); await p.waitForTimeout(300); await click(p, '[role=menuitem]:has-text("Configure")'); }
    await p.waitForTimeout(600);
  }],
  ['tg-general', 'gateways/Telegram%20Bot'],
  ['tg-credentials', 'gateways/Telegram%20Bot', async (p: Page) => { await click(p, '[role=tab]:has-text("Credentials")'); }],
  ['tg-recipients', 'gateways/Telegram%20Bot', async (p: Page) => { await click(p, '[role=tab]:has-text("Recipients")'); }],
  ['tg-channel', 'gateways/Telegram%20Bot', async (p: Page) => { await click(p, '[role=tab]:has-text("Channel")'); }],
  ['gw-new-telegram', 'gateways/new?service=telegram'],
  ['wa-gw-channel', 'gateways/WA-Settings', async (p: Page) => { await click(p, '[role=tab]:has-text("Channel")'); }],
  ['int-list', 'integrations'],
  ['int-detail', 'integrations/GitHub%20Main'],
  ['int-detail-credentials', 'integrations/GitHub%20Main', async (p: Page) => { await click(p, '[role=tab]:has-text("Credentials")'); }],
  ['int-services', 'integration-services'],
  ['int-service-form', 'integration-services/telegram'],
];

export const GEOMETRY_ROUTES: GeometryRoute[] = S.map(([id, path, act]) => ({ id, path, act }));
