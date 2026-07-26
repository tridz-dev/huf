import { expect, Page } from '@playwright/test';

/**
 * Navigate to an app page on the live site. The deployed baseURL ends in
 * `/huf/`, so the leading slash is stripped and the path resolves under the
 * app mount (e.g. '/agents' → <site>/huf/agents).
 */
export async function gotoHuf(page: Page, path: string) {
  await page.goto(path.replace(/^\//, ''));
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
}

/** Wait for any loading spinner to disappear. */
export async function waitForSpinner(page: Page) {
  await page.waitForSelector('.animate-spin', { state: 'detached', timeout: 10000 }).catch(() => {});
}

/** Wait for a sonner toast whose text matches `pattern`. */
export async function waitForToast(page: Page, pattern: RegExp | string, timeout = 10000) {
  const toast = page.locator('[data-sonner-toast]').filter({ hasText: pattern });
  await expect(toast.first()).toBeVisible({ timeout });
}

/**
 * Call a whitelisted Frappe method from inside the page (inherits the
 * session cookie and CSRF token). Unwraps `message.data ?? message` like the
 * frontend's own API layer does.
 */
export async function apiCall<T = unknown>(page: Page, method: string, args: Record<string, unknown> = {}): Promise<T> {
  return page.evaluate(
    async ({ method, args }) => {
      const res = await fetch(`/api/method/${method}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Frappe-CSRF-Token': (window as unknown as { csrf_token?: string }).csrf_token ?? '',
        },
        body: JSON.stringify(args),
      });
      if (!res.ok) {
        throw new Error(`apiCall ${method} failed: HTTP ${res.status} ${await res.text()}`);
      }
      const json = await res.json();
      return json?.message?.data ?? json?.message;
    },
    { method, args },
  ) as Promise<T>;
}

/** frappe.client.get_list convenience wrapper. */
export async function getList<T = unknown>(
  page: Page,
  doctype: string,
  args: Record<string, unknown> = {},
): Promise<T[]> {
  const result = await apiCall<T[]>(page, 'frappe.client.get_list', { doctype, ...args });
  return Array.isArray(result) ? result : [];
}
