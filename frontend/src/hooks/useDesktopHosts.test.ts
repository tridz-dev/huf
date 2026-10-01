// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

const listDesktopHosts = vi.fn();
vi.mock('@/services/desktopHostApi', () => ({
  listDesktopHosts: () => listDesktopHosts(),
}));

import { DESKTOP_HOSTS_POLL_MS, __resetDesktopHostsForTests, useDesktopHosts } from './useDesktopHosts';

const host = (online: boolean) => ({
  device_id: 'd1',
  label: 'Laptop',
  online,
  last_seen: 1,
  remote_control: true,
  mode: 'ask',
});

beforeEach(() => {
  vi.useFakeTimers();
  listDesktopHosts.mockReset();
  __resetDesktopHostsForTests();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('useDesktopHosts', () => {
  it('fetches once for many subscribers and polls on an interval', async () => {
    listDesktopHosts.mockResolvedValue([host(true)]);
    const a = renderHook(() => useDesktopHosts(true));
    const b = renderHook(() => useDesktopHosts(true));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(listDesktopHosts).toHaveBeenCalledTimes(1);
    expect(a.result.current.byDevice.get('d1')?.online).toBe(true);
    expect(b.result.current.loaded).toBe(true);

    listDesktopHosts.mockResolvedValue([host(false)]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DESKTOP_HOSTS_POLL_MS);
    });
    expect(listDesktopHosts).toHaveBeenCalledTimes(2);
    expect(a.result.current.byDevice.get('d1')?.online).toBe(false);
  });

  it('stops polling when the last subscriber unmounts', async () => {
    listDesktopHosts.mockResolvedValue([host(true)]);
    const a = renderHook(() => useDesktopHosts(true));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    a.unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DESKTOP_HOSTS_POLL_MS * 3);
    });
    expect(listDesktopHosts).toHaveBeenCalledTimes(1);
  });

  it('does not fetch when disabled', async () => {
    renderHook(() => useDesktopHosts(false));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DESKTOP_HOSTS_POLL_MS * 2);
    });
    expect(listDesktopHosts).not.toHaveBeenCalled();
  });

  it('keeps the last list and flags error when a poll fails', async () => {
    listDesktopHosts.mockResolvedValueOnce([host(true)]);
    const a = renderHook(() => useDesktopHosts(true));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    listDesktopHosts.mockRejectedValueOnce(new Error('net'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DESKTOP_HOSTS_POLL_MS);
    });
    expect(a.result.current.error).toBe(true);
    expect(a.result.current.hosts).toHaveLength(1);
  });
});
