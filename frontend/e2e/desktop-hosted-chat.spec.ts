import { test, expect, type Page } from '@playwright/test';
import { goto, waitForContent, mockOfflineApis } from './helpers';

// Deterministic, offline stage for desktop-hosted conversations (Desktop Remote Sessions):
// host badge in the rail and header, the permission-mode picker, and the composer banners for a run
// the server declines (desktop_offline / workspace_changed / remote_disabled). Every backend call is
// mocked at the network layer, so this exercises the real SPA against fixed server answers only.

const AGENT = {
  name: 'AGT-0001',
  agent_name: 'Dev Agent',
  provider: 'OpenAI',
  model: 'gpt-4o',
  disabled: 0,
  allow_chat: 1,
  run_immediately: 0,
  persist_conversation: 1,
  modified: '2026-09-30 10:00:00',
};

const HOSTED = {
  name: 'conv-1',
  title: 'Fix the build',
  agent: 'AGT-0001',
  model: 'gpt-4o',
  channel: 'Chat',
  execution_host: 'desktop',
  host_device_id: 'dev1',
  host_label: 'Laptop - repo',
  modified: '2026-09-30 10:00:00',
};

const json = (body: unknown) => ({ contentType: 'application/json', body: JSON.stringify(body) });

async function mockHostedChat(page: Page, host: Record<string, unknown> = {}) {
  await mockOfflineApis(page);
  await page.route('**/api/resource/Agent/AGT-0001**', (r) => r.fulfill(json({ data: AGENT })));
  await page.route('**/api/resource/Agent?**', (r) => r.fulfill(json({ data: [AGENT] })));
  await page.route('**/api/resource/Agent%20Conversation/conv-1**', (r) => r.fulfill(json({ data: HOSTED })));
  await page.route('**/api/resource/Agent%20Conversation?**', (r) => r.fulfill(json({ data: [HOSTED] })));
  await page.route('**/api/method/huf.ai.desktop_sessions.list_desktop_hosts**', (r) =>
    r.fulfill(
      json({
        message: [
          {
            device_id: 'dev1',
            label: 'Laptop',
            online: true,
            last_seen: Date.now(),
            remote_control: true,
            mode: 'ask',
            ...host,
          },
        ],
      }),
    ),
  );
}

test.describe('Desktop-hosted chat', () => {
  test('shows the host badge in the rail and header with an online dot', async ({ page }) => {
    await mockHostedChat(page);
    await goto(page, '/chat/conv-1');
    await waitForContent(page);
    const badges = page.getByTestId('desktop-host-badge');
    await expect(badges.first()).toBeVisible();
    await expect(page.getByTestId('host-status-dot').first()).toHaveAttribute('data-online', 'true');
    await expect(page.getByText('Laptop - repo').first()).toBeVisible();
  });

  test('an offline device shows a grey dot', async ({ page }) => {
    await mockHostedChat(page, { online: false, remote_control: false });
    await goto(page, '/chat/conv-1');
    await waitForContent(page);
    await expect(page.getByTestId('host-status-dot').first()).toHaveAttribute('data-online', 'false');
  });

  test('changing the permission mode shows the mode the desktop confirmed', async ({ page }) => {
    await mockHostedChat(page);
    let body: { device_id?: string; mode?: string } = {};
    await page.route('**/api/method/huf.ai.desktop_sessions.set_desktop_permission_mode**', (r) => {
      body = r.request().postDataJSON();
      return r.fulfill(json({ message: { ok: true, applied_mode: 'full', device_id: 'dev1' } }));
    });
    await goto(page, '/chat/conv-1');
    await waitForContent(page);
    const trigger = page.getByRole('combobox', { name: 'Permission mode' });
    await expect(trigger).toContainText('Ask');
    await trigger.click();
    await page.getByRole('option', { name: 'Full' }).click();
    await expect(trigger).toContainText('Full');
    expect(body).toEqual({ device_id: 'dev1', mode: 'full' });
  });

  test('a refused mode change is shown, not hidden', async ({ page }) => {
    await mockHostedChat(page);
    await page.route('**/api/method/huf.ai.desktop_sessions.set_desktop_permission_mode**', (r) =>
      r.fulfill(json({ message: { ok: false, error: { code: 'mode_not_applied', message: 'no', applied_mode: 'ask' } } })),
    );
    await goto(page, '/chat/conv-1');
    await waitForContent(page);
    await page.getByRole('combobox', { name: 'Permission mode' }).click();
    await page.getByRole('option', { name: 'Full' }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'did not apply that mode' })).toBeVisible();
  });

  test('desktop_offline puts a banner above the composer and Retry resends', async ({ page }) => {
    await mockHostedChat(page);
    let calls = 0;
    await page.route('**/api/method/huf.ai.agent_chat.send_message_to_conversation**', (r) => {
      calls += 1;
      if (calls === 1) {
        return r.fulfill(
          json({
            message: {
              success: false,
              queued: false,
              error: 'desktop_offline',
              code: 'desktop_offline',
              message: 'Laptop - repo is offline.',
              conversation_id: 'conv-1',
              last_seen: Date.now() - 3 * 60_000,
              host_device_id: 'dev1',
              host_label: 'Laptop - repo',
            },
          }),
        );
      }
      return r.fulfill(
        json({ message: { success: true, queued: true, status: 'Queued', conversation_id: 'conv-1', agent_run_id: 'run-1', sequence: 1 } }),
      );
    });
    await goto(page, '/chat/conv-1');
    await waitForContent(page);
    const composer = page.getByPlaceholder('Write a message…');
    await composer.fill('list the files');
    await composer.press('Enter');
    const banner = page.getByTestId('desktop-run-banner');
    await expect(banner).toContainText('Laptop - repo is offline');
    await expect(banner).toContainText('Last seen 3 min ago');
    await expect(composer).toHaveValue('list the files');
    await banner.getByRole('button', { name: /Retry/ }).click();
    await expect(banner).toBeHidden();
    expect(calls).toBe(2);
  });

  test('workspace_changed offers a rebind that resends', async ({ page }) => {
    await mockHostedChat(page);
    let sends = 0;
    await page.route('**/api/method/huf.ai.agent_chat.send_message_to_conversation**', (r) => {
      sends += 1;
      return sends === 1
        ? r.fulfill(json({ message: { success: false, code: 'workspace_changed', error: 'workspace_changed', message: 'x', conversation_id: 'conv-1' } }))
        : r.fulfill(json({ message: { success: true, queued: true, status: 'Queued', conversation_id: 'conv-1', agent_run_id: 'run-2', sequence: 2 } }));
    });
    let rebound = false;
    await page.route('**/api/method/huf.ai.desktop_sessions.rebind_desktop_conversation**', (r) => {
      rebound = true;
      return r.fulfill(json({ message: { ok: true, conversation: 'conv-1', host_label: 'Laptop - other' } }));
    });
    await goto(page, '/chat/conv-1');
    await waitForContent(page);
    const composer = page.getByPlaceholder('Write a message…');
    await composer.fill('go');
    await composer.press('Enter');
    await page.getByRole('button', { name: 'Rebind and retry' }).click();
    await expect(page.getByTestId('desktop-run-banner')).toBeHidden();
    expect(rebound).toBe(true);
    expect(sends).toBe(2);
  });

  test('remote_disabled by the desktop tells the user to enable remote control there', async ({ page }) => {
    await mockHostedChat(page);
    await page.route('**/api/method/huf.ai.agent_chat.send_message_to_conversation**', (r) =>
      r.fulfill(json({ message: { success: false, code: 'remote_disabled', error: 'remote_disabled', message: 'x', disabled_by: 'desktop' } })),
    );
    await goto(page, '/chat/conv-1');
    await waitForContent(page);
    const composer = page.getByPlaceholder('Write a message…');
    await composer.fill('go');
    await composer.press('Enter');
    await expect(page.getByTestId('desktop-run-banner')).toContainText('Turn on remote control in Huf Desktop');
  });

  test('remote_disabled by the agent links to the agent permissions', async ({ page }) => {
    await mockHostedChat(page);
    await page.route('**/api/method/huf.ai.agent_chat.send_message_to_conversation**', (r) =>
      r.fulfill(json({ message: { success: false, code: 'remote_disabled', error: 'remote_disabled', message: 'x', disabled_by: 'agent' } })),
    );
    await goto(page, '/chat/conv-1');
    await waitForContent(page);
    const composer = page.getByPlaceholder('Write a message…');
    await composer.fill('go');
    await composer.press('Enter');
    const link = page.getByTestId('desktop-run-banner').getByRole('link');
    await expect(link).toHaveAttribute('href', /\/agents\/AGT-0001#permissions$/);
  });
});
