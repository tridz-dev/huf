// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { UseFormReturn } from 'react-hook-form';
import type { AgentFormValues } from '../types';
import { AccessTab, type AccessTabProps } from './AccessTab';
import { renderTab } from './testHarness';

vi.mock('@/components/ui/select', () => import('./selectMock').then((m) => m.selectMock()));

function mount(values: Partial<AgentFormValues> = {}, props: Partial<AccessTabProps> = {}) {
  let form!: UseFormReturn<AgentFormValues>;
  renderTab((f) => <AccessTab form={f} {...props} />, values, (f) => { form = f; });
  return () => form;
}

describe('AccessTab', () => {
  it('summarises who can use it', () => {
    mount({ allowed_users: ['a@x.com'], allowed_roles: ['Sales'] });
    expect(screen.getByTestId('who-status')).toHaveTextContent('Only 1 user(s) and 1 role(s)');
  });

  it('toggles everyone signed in and public access', async () => {
    const f = mount();
    await userEvent.click(screen.getByRole('switch', { name: 'Everyone who is signed in' }));
    expect(f().getValues('allow_all_users')).toBe(true);
    await userEvent.click(screen.getByRole('switch', { name: 'Anyone with the link, no login' }));
    expect(f().getValues('allow_guest')).toBe(true);
  });

  it('reveals the execution profile and shared dir limit only when code execution is on', async () => {
    mount();
    expect(screen.queryByText('Execution profile')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('switch', { name: 'Run code' }));
    expect(screen.getByText('Execution profile')).toBeInTheDocument();
    expect(screen.getByText('Shared folder limit (MB)')).toBeInTheDocument();
  });

  it('reveals SSH connections when SSH is on', () => {
    mount({ allow_ssh: true });
    expect(screen.getByText('Allowed SSH connections')).toBeInTheDocument();
  });

  it('shows conversation data permission only when conversation data is enabled', () => {
    mount({ enable_conversation_data: true });
    expect(screen.getByText('Conversation data API permission')).toBeInTheDocument();
  });

  it('desktop access: master switch sets all seven to ask and notifies the page', async () => {
    const onChange = vi.fn();
    const f = mount({ desktop_access_cli: 'off', desktop_access_files: 'off', desktop_access_skills: 'off', desktop_access_local_mcp: 'off',
      desktop_access_browser: 'off', desktop_access_installs: 'off', desktop_access_processes: 'off' }, { onDesktopAccessChange: onChange });
    await userEvent.click(screen.getByRole('switch', { name: 'Use Huf Desktop' }));
    expect(f().getValues('desktop_access_cli')).toBe('ask');
    expect(onChange).toHaveBeenCalledTimes(7);
    expect(screen.getByText('Run commands')).toBeInTheDocument();
  });

  it('desktop access: per-capability change and remote control fire callbacks', async () => {
    const onRemote = vi.fn();
    const onChange = vi.fn();
    mount({}, { onRemoteDesktopChange: onRemote, onDesktopAccessChange: onChange });
    await userEvent.click(screen.getByRole('switch', { name: 'Allow remote desktop control' }));
    expect(onRemote).toHaveBeenCalledWith(true);
    await userEvent.click(screen.getAllByRole('option', { name: 'Off' })[0]);
    expect(onChange).toHaveBeenCalledWith('desktop_access_cli', 'off');
  });

  it('desktop controls stay disabled until ready', () => {
    mount({}, { desktopAccessStatus: 'loading' });
    expect(screen.getByRole('switch', { name: 'Use Huf Desktop' })).toBeDisabled();
  });
});
