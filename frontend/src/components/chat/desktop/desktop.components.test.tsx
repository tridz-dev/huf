// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('sonner', () => ({ toast: { success: (...a: unknown[]) => toastSuccess(...a), error: (...a: unknown[]) => toastError(...a) } }));

const setMode = vi.fn();
vi.mock('@/services/desktopHostApi', async () => {
  const actual = await vi.importActual<typeof import('@/services/desktopHostApi')>('@/services/desktopHostApi');
  return { ...actual, setDesktopPermissionMode: (...a: unknown[]) => setMode(...a), listDesktopHosts: vi.fn().mockResolvedValue([]) };
});

// Radix Select's popper never settles under jsdom (the test hangs on open), so the picker is
// exercised through a native <select> stand-in. The control's own logic is what is under test.
vi.mock('@/components/ui/select', async () => {
  const React = await import('react');
  type Ctx = { value?: string; onValueChange?: (v: string) => void; disabled?: boolean };
  const C = React.createContext<Ctx>({});
  return {
    Select: ({ value, onValueChange, disabled, children }: React.PropsWithChildren<Ctx>) =>
      React.createElement(C.Provider, { value: { value, onValueChange, disabled } }, children),
    SelectTrigger: ({ children, ...rest }: React.PropsWithChildren<Record<string, unknown>>) => {
      const ctx = React.useContext(C);
      return React.createElement('span', null, React.createElement('button', { role: 'combobox', disabled: ctx.disabled, ...rest }, ctx.value ?? ''), children);
    },
    SelectValue: () => null,
    SelectContent: ({ children }: React.PropsWithChildren) => React.createElement('div', { role: 'listbox' }, children),
    SelectItem: ({ value, children }: React.PropsWithChildren<{ value: string }>) => {
      const ctx = React.useContext(C);
      return React.createElement('button', { role: 'option', onClick: () => ctx.onValueChange?.(value) }, children);
    },
  };
});

let hostsState: { hosts: unknown[]; byDevice: Map<string, unknown>; loaded: boolean; error: boolean; refresh: () => Promise<void> };
const refresh = vi.fn().mockResolvedValue(undefined);
vi.mock('@/hooks/useDesktopHosts', () => ({
  useDesktopHosts: () => hostsState,
  refreshDesktopHosts: () => refresh(),
}));

import { DesktopRunError } from '@/services/desktopHostApi';
import { DesktopRunBanner } from './DesktopRunBanner';
import { DesktopHostBadge } from './DesktopHostBadge';
import { DesktopPermissionModeControl } from './DesktopPermissionModeControl';

function setHosts(hosts: Array<Record<string, unknown>>, loaded = true) {
  hostsState = {
    hosts,
    byDevice: new Map(hosts.map((h) => [h.device_id as string, h])),
    loaded,
    error: false,
    refresh,
  };
}

beforeAll(() => {
  // Radix Select needs these in jsdom.
  Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture || (() => false);
  Element.prototype.setPointerCapture = Element.prototype.setPointerCapture || (() => {});
  Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture || (() => {});
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {});
});

beforeEach(() => {
  toastSuccess.mockReset();
  toastError.mockReset();
  setMode.mockReset();
  refresh.mockClear();
  setHosts([{ device_id: 'd1', label: 'Laptop', online: true, last_seen: Date.now(), remote_control: true, mode: 'ask' }]);
});
afterEach(() => vi.clearAllMocks());

describe('DesktopHostBadge', () => {
  it('shows the label and an online dot', () => {
    render(<DesktopHostBadge host={{ deviceId: 'd1', label: 'Laptop - repo' }} />);
    expect(screen.getByText('Laptop - repo')).toBeInTheDocument();
    expect(screen.getByTestId('host-status-dot')).toHaveAttribute('data-online', 'true');
  });

  it('shows offline for a device that is not online, and unknown before the first poll', () => {
    setHosts([{ device_id: 'd1', online: false, last_seen: 1, remote_control: false, mode: null }]);
    const { unmount } = render(<DesktopHostBadge host={{ deviceId: 'd1', label: 'Laptop' }} />);
    expect(screen.getByTestId('host-status-dot')).toHaveAttribute('data-online', 'false');
    unmount();
    setHosts([], false);
    render(<DesktopHostBadge host={{ deviceId: 'd1', label: 'Laptop' }} compact />);
    expect(screen.getByTestId('host-status-dot')).toHaveAttribute('data-online', 'unknown');
    expect(screen.getByTitle(/Runs on Laptop \(checking\)/)).toBeInTheDocument();
  });

  it('a device missing from the list is offline', () => {
    setHosts([]);
    render(<DesktopHostBadge host={{ deviceId: 'gone', label: 'Old PC' }} compact />);
    expect(screen.getByTestId('host-status-dot')).toHaveAttribute('data-online', 'false');
  });
});

describe('DesktopRunBanner', () => {
  const handlers = () => ({ onRetry: vi.fn(), onRebind: vi.fn(), onDismiss: vi.fn() });

  it('offline: shows last seen and a Retry button', async () => {
    const h = handlers();
    const err = new DesktopRunError('desktop_offline', 'x', { lastSeen: Date.now() - 5 * 60_000, hostLabel: 'Laptop - repo' });
    render(<MemoryRouter><DesktopRunBanner error={err} agentName="A" {...h} /></MemoryRouter>);
    expect(screen.getByText('Laptop - repo is offline')).toBeInTheDocument();
    expect(screen.getByText(/Last seen 5 min ago/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Retry/ }));
    expect(h.onRetry).toHaveBeenCalledOnce();
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(h.onDismiss).toHaveBeenCalledOnce();
  });

  it('workspace_changed: offers Rebind and retry, not Retry', async () => {
    const h = handlers();
    render(<MemoryRouter><DesktopRunBanner error={new DesktopRunError('workspace_changed', 'x')} {...h} /></MemoryRouter>);
    expect(screen.queryByRole('button', { name: /^Retry/ })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Rebind and retry' }));
    expect(h.onRebind).toHaveBeenCalledOnce();
  });

  it('remote_disabled by the desktop tells the user to enable it on the desktop', () => {
    render(<MemoryRouter><DesktopRunBanner error={new DesktopRunError('remote_disabled', 'x', { disabledBy: 'desktop' })} {...handlers()} /></MemoryRouter>);
    expect(screen.getByText('Remote control is off on the desktop')).toBeInTheDocument();
    expect(screen.getByText(/Turn on remote control in Huf Desktop/)).toBeInTheDocument();
  });

  it('remote_disabled by the agent links to the agent permissions', () => {
    render(<MemoryRouter><DesktopRunBanner error={new DesktopRunError('remote_disabled', 'x', { disabledBy: 'agent' })} agentName="My Agent" {...handlers()} /></MemoryRouter>);
    expect(screen.getByText('This agent does not allow remote control')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /agent.s permissions/ })).toHaveAttribute('href', '/agents/My%20Agent#permissions');
  });

  it('shows a note and disables actions while busy', () => {
    render(<MemoryRouter><DesktopRunBanner error={new DesktopRunError('desktop_offline', 'x')} busy note="A turn is still running." {...handlers()} /></MemoryRouter>);
    expect(screen.getByText('A turn is still running.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Retry/ })).toBeDisabled();
  });
});

describe('DesktopPermissionModeControl', () => {
  async function pick(name: string) {
    const list = screen.getByRole('listbox');
    await userEvent.click(within(list).getByRole('option', { name }));
  }

  it('shows the desktop mode and applies a change, showing the confirmed mode', async () => {
    setMode.mockResolvedValue({ ok: true, appliedMode: 'full' });
    render(<DesktopPermissionModeControl deviceId="d1" />);
    expect(screen.getByRole('combobox', { name: 'Permission mode' })).toHaveTextContent('ask');
    await pick('Full');
    await waitFor(() => expect(setMode).toHaveBeenCalledWith('d1', 'full'));
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Permission mode' })).toHaveTextContent('full'));
    expect(toastSuccess).toHaveBeenCalledWith('Permission mode is now Full');
    expect(refresh).toHaveBeenCalled();
  });

  it('mode_not_applied shows the error and the mode the desktop actually kept', async () => {
    setMode.mockResolvedValue({ ok: false, error: { code: 'mode_not_applied', message: 'no', appliedMode: 'ask' } });
    render(<DesktopPermissionModeControl deviceId="d1" />);
    await pick('Full');
    expect(await screen.findByRole('alert')).toHaveTextContent('The desktop did not apply that mode. It is still on Ask.');
    expect(screen.getByRole('combobox', { name: 'Permission mode' })).toHaveTextContent('ask');
    expect(toastError).toHaveBeenCalled();
  });

  it('remote_disabled from the server is explained', async () => {
    setMode.mockResolvedValue({ ok: false, error: { code: 'remote_disabled', message: 'off' } });
    render(<DesktopPermissionModeControl deviceId="d1" />);
    await pick('Auto');
    expect(await screen.findByRole('alert')).toHaveTextContent(/Remote control is off on this desktop/);
  });

  it('is disabled when the desktop is offline or remote control is off', () => {
    setHosts([{ device_id: 'd1', label: 'Laptop', online: false, last_seen: 1, remote_control: true, mode: 'ask' }]);
    const { unmount } = render(<DesktopPermissionModeControl deviceId="d1" />);
    expect(screen.getByRole('combobox', { name: 'Permission mode' })).toBeDisabled();
    unmount();
    setHosts([{ device_id: 'd1', label: 'Laptop', online: true, last_seen: 1, remote_control: false, mode: 'ask' }]);
    render(<DesktopPermissionModeControl deviceId="d1" />);
    const trigger = screen.getByRole('combobox', { name: 'Permission mode' });
    expect(trigger).toBeDisabled();
    expect(trigger).toHaveAttribute('title', 'Remote control is off on this desktop.');
  });
});
