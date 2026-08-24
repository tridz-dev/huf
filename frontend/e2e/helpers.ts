import { Page } from '@playwright/test';

/**
 * Navigate to an app page and wait for it to settle.
 * Paths are given ROI-style with a leading slash ('/agents'); they are
 * resolved against the configured baseURL (…/huf/), so the leading slash is
 * stripped to keep the router basename intact.
 */
export async function goto(page: Page, path: string) {
  await page.goto(path.replace(/^\//, ''));
  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
}

/** Dismiss any loading spinners by waiting for them to disappear */
export async function waitForContent(page: Page) {
  await page.waitForSelector('.animate-spin', { state: 'detached', timeout: 6000 }).catch(() => {});
}

/**
 * All capabilities referenced by the sidebar nav (see app-sidebar.tsx).
 * Returned by the mocked get_me so every nav item renders offline.
 */
export const ALL_CAPABILITIES = [
  'agent.use',
  'agent.view_all',
  'flows.use',
  'chat.use',
  'users.manage',
  'roles.manage',
  'system.providers.manage',
  'system.integrations.manage',
  'system.mcp.manage',
  'data.tables.manage',
  'data.records.view_own',
  'data.records.view_all',
];

/**
 * Mock every backend call the SPA makes so pages render without a Frappe
 * server. Boot/auth endpoints get realistic responses; everything else gets
 * an empty-but-valid Frappe shape (resource list → {data: []}, method call →
 * {message: []}). Register catch-alls first, specifics after: Playwright
 * matches routes in reverse registration order.
 */
export async function mockOfflineApis(page: Page) {
  // Generic catch-alls (registered first, lowest precedence).
  await page.route('**/api/resource/**', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
    }
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: {} }) });
  });
  // Single-document GETs (/api/resource/<Doctype>/<name>) get a doc-shaped
  // response, not a list.
  await page.route('**/api/resource/*/*', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: {} }) });
    }
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: {} }) });
  });
  await page.route('**/api/method/**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ message: [] }) }),
  );

  // Streaming availability probe (avoids the "Streaming not working" toast).
  await page.route('**/huf/stream/ping', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true }) }),
  );

  // Auth boot: frappe-js-sdk auth.getLoggedInUser().
  await page.route('**/api/method/frappe.auth.get_logged_user**', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Administrator' }),
    }),
  );

  // User doc fetched right after login check.
  await page.route('**/api/resource/User/**', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          name: 'Administrator',
          email: 'admin@example.com',
          full_name: 'Administrator',
          user_image: null,
        },
      }),
    }),
  );

  // HUF identity + capabilities (drives sidebar visibility).
  await page.route('**/api/method/huf.permissions.get_me**', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        message: {
          user: 'Administrator',
          full_name: 'Administrator',
          huf_role: 'Huf Admin',
          capabilities: ALL_CAPABILITIES,
        },
      }),
    }),
  );

  // Sidebar agent count badge.
  await page.route('**/api/method/frappe.client.get_count**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ message: 0 }) }),
  );

  // Executions page analytics strip (ExecutionAnalyticsDashboard): the
  // generic `{message: []}` catch-all doesn't match this endpoint's
  // object-shaped response, and the component dereferences `summary.*`
  // unconditionally once `data` is truthy — an array is truthy too, so it
  // renders past the loading state straight into a crash. Needs its own
  // well-shaped mock.
  await page.route('**/api/method/huf.ai.agent_run_analytics_api.get_execution_analytics**', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        message: {
          summary: {
            run_count: 0,
            success_count: 0,
            failed_count: 0,
            input_tokens: 0,
            output_tokens: 0,
            cached_tokens: 0,
            total_cost: 0,
            duration_ms_sum: 0,
            duration_count: 0,
            success_rate: null,
            average_duration_ms: null,
            cache_ratio: null,
          },
          series: [],
          breakdowns: [],
          metadata: { granularity: 'hour', freshness: null, source: 'scheduled_rollup' },
        },
      }),
    }),
  );
}
