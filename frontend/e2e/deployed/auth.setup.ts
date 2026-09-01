import { test as setup } from '@playwright/test';

const authFile = 'e2e/.auth/user.json';

setup('authenticate', async ({ page, baseURL }) => {
  const user = process.env.E2E_USER || 'Administrator';
  const password = process.env.E2E_PASSWORD || 'admin';

  // Login lives at the site root, not under /huf, so build an absolute URL
  // rather than relying on baseURL-relative resolution.
  const origin = new URL(baseURL!).origin;

  await page.goto(`${origin}/login`);
  await page.fill('#login_email, input[data-fieldname="usr"], input[type="email"]', user);
  await page.fill('input[type="password"]', password);
  await page.click('button:has-text("Login")');
  await page.waitForLoadState('networkidle');

  // Land explicitly on the React app to confirm the session is usable there.
  // Don't rely on the "Dashboard" nav label being VISIBLE -- the sidebar can
  // load in collapsed/icon-only mode (its label span has a
  // `group-data-[collapsible=icon]:hidden` class), so the same text exists
  // in the DOM but isn't visible, even for a successfully authenticated
  // session. Waiting on the URL settling into the app is a more robust
  // signal that the session is usable here (confirmed against a real bench).
  await page.goto('');
  await page.waitForURL(/\/huf\/?($|[?#])/, { timeout: 15000 });
  await page.waitForLoadState('networkidle');

  await page.context().storageState({ path: authFile });
});
