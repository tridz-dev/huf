import { beforeEach, describe, expect, it, vi } from 'vitest';

const post = vi.fn();
const get = vi.fn();
vi.mock('@/lib/frappe-sdk', () => ({
  call: { post: (...a: unknown[]) => post(...a), get: (...a: unknown[]) => get(...a) },
  db: {},
}));

import {
  DesktopRunError,
  formatLastSeen,
  listDesktopHosts,
  parseDesktopRunFailure,
  rebindDesktopConversation,
  setDesktopPermissionMode,
} from './desktopHostApi';
import { hostFromConversation } from './chatApi';

beforeEach(() => {
  post.mockReset();
  get.mockReset();
});

describe('parseDesktopRunFailure', () => {
  it('reads desktop_offline with last_seen and the host', () => {
    const err = parseDesktopRunFailure({
      success: false,
      error: 'desktop_offline',
      code: 'desktop_offline',
      message: 'Laptop is offline.',
      last_seen: 1_700_000_000_000,
      host_device_id: 'abc',
      host_label: 'Laptop - repo',
    });
    expect(err).toBeInstanceOf(DesktopRunError);
    expect(err?.code).toBe('desktop_offline');
    expect(err?.lastSeen).toBe(1_700_000_000_000);
    expect(err?.hostLabel).toBe('Laptop - repo');
  });

  it('reads remote_disabled with which switch is off', () => {
    expect(parseDesktopRunFailure({ success: false, code: 'remote_disabled', disabled_by: 'agent' })?.disabledBy).toBe(
      'agent',
    );
    expect(parseDesktopRunFailure({ success: false, code: 'remote_disabled', disabled_by: 'desktop' })?.disabledBy).toBe(
      'desktop',
    );
  });

  it('recognises workspace_changed and permission_denied', () => {
    expect(parseDesktopRunFailure({ success: false, code: 'workspace_changed' })?.code).toBe('workspace_changed');
    expect(parseDesktopRunFailure({ success: false, code: 'permission_denied' })?.code).toBe('permission_denied');
  });

  it('ignores ordinary failures, successes and junk so the existing error path is unchanged', () => {
    expect(parseDesktopRunFailure({ success: false, error: 'Model quota exceeded' })).toBeNull();
    expect(parseDesktopRunFailure({ success: true, code: 'desktop_offline' })).toBeNull();
    expect(parseDesktopRunFailure(undefined)).toBeNull();
    expect(parseDesktopRunFailure('desktop_offline')).toBeNull();
  });
});

describe('formatLastSeen', () => {
  const now = 1_700_000_000_000;
  it('formats relative times', () => {
    expect(formatLastSeen(now - 10_000, now)).toBe('just now');
    expect(formatLastSeen(now - 5 * 60_000, now)).toBe('5 min ago');
    expect(formatLastSeen(now - 3 * 3_600_000, now)).toBe('3 h ago');
    expect(formatLastSeen(now - 2 * 86_400_000, now)).toBe('2 d ago');
  });
  it('handles a missing timestamp', () => {
    expect(formatLastSeen(null)).toBe('not seen recently');
  });
});

describe('hostFromConversation', () => {
  it('returns a host only for desktop-hosted rows', () => {
    expect(hostFromConversation({ execution_host: 'desktop', host_device_id: 'd1', host_label: 'L' })).toEqual({
      deviceId: 'd1',
      label: 'L',
    });
    expect(hostFromConversation({ execution_host: 'server', host_device_id: null, host_label: null })).toBeUndefined();
    expect(hostFromConversation({})).toBeUndefined();
  });
});

describe('endpoints', () => {
  it('listDesktopHosts unwraps message', async () => {
    get.mockResolvedValue({ message: [{ device_id: 'd1', label: 'L', online: true, last_seen: 1, remote_control: true, mode: 'ask' }] });
    const hosts = await listDesktopHosts();
    expect(hosts).toHaveLength(1);
    expect(get).toHaveBeenCalledWith('huf.ai.desktop_sessions.list_desktop_hosts');
  });

  it('setDesktopPermissionMode returns the confirmed mode', async () => {
    post.mockResolvedValue({ message: { ok: true, applied_mode: 'full', device_id: 'd1' } });
    const r = await setDesktopPermissionMode('d1', 'full');
    expect(r).toEqual({ ok: true, appliedMode: 'full' });
    expect(post).toHaveBeenCalledWith('huf.ai.desktop_sessions.set_desktop_permission_mode', {
      device_id: 'd1',
      mode: 'full',
    });
  });

  it('setDesktopPermissionMode surfaces mode_not_applied with the mode the desktop kept', async () => {
    post.mockResolvedValue({
      message: { ok: false, error: { code: 'mode_not_applied', message: 'no', applied_mode: 'ask' } },
    });
    const r = await setDesktopPermissionMode('d1', 'full');
    expect(r.ok).toBe(false);
    expect(r.error?.code).toBe('mode_not_applied');
    expect(r.error?.appliedMode).toBe('ask');
  });

  it('setDesktopPermissionMode surfaces remote_disabled', async () => {
    post.mockResolvedValue({ message: { ok: false, error: { code: 'remote_disabled', message: 'off' } } });
    const r = await setDesktopPermissionMode('d1', 'auto');
    expect(r.error?.code).toBe('remote_disabled');
  });

  it('rebindDesktopConversation maps ok and errors', async () => {
    post.mockResolvedValueOnce({ message: { ok: true, conversation: 'c', host_label: 'L - ws' } });
    expect(await rebindDesktopConversation('c')).toEqual({ ok: true, hostLabel: 'L - ws' });
    post.mockResolvedValueOnce({ message: { ok: false, error: { code: 'run_in_progress', message: 'wait' } } });
    const r = await rebindDesktopConversation('c');
    expect(r.ok).toBe(false);
    expect(r.error?.code).toBe('run_in_progress');
  });
});
