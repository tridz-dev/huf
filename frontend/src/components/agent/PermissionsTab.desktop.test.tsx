// @vitest-environment jsdom
//
// The "Desktop access" card on the Permissions tab: seven off/ask/allowed selectors and the remote
// control switch, bound to the agent form so they save with the rest of the tab.
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { useForm, type UseFormReturn } from 'react-hook-form';

// Radix Select's popper never settles under jsdom, so use a native stand-in for the pickers.
vi.mock('@/components/ui/select', async () => {
  const React = await import('react');
  type Ctx = { value?: string; onValueChange?: (v: string) => void; disabled?: boolean };
  const C = React.createContext<Ctx>({});
  return {
    Select: ({ value, onValueChange, disabled, children }: React.PropsWithChildren<Ctx>) =>
      React.createElement(C.Provider, { value: { value, onValueChange, disabled } }, React.createElement('div', null, children)),
    SelectTrigger: ({ children, ...rest }: React.PropsWithChildren<Record<string, unknown>>) => {
      const ctx = React.useContext(C);
      return React.createElement('button', { type: 'button', role: 'combobox', disabled: ctx.disabled, ...rest }, ctx.value ?? '', children);
    },
    SelectValue: () => null,
    SelectContent: ({ children }: React.PropsWithChildren) => React.createElement('div', { role: 'listbox' }, children),
    SelectItem: ({ value, children }: React.PropsWithChildren<{ value: string }>) => {
      const ctx = React.useContext(C);
      return React.createElement('button', { type: 'button', role: 'option', onClick: () => ctx.onValueChange?.(value) }, children);
    },
  };
});
vi.mock('@/services/agentApi', () => ({
  searchUsers: vi.fn().mockResolvedValue([]),
  searchRoles: vi.fn().mockResolvedValue([]),
  fetchUsersByName: vi.fn().mockResolvedValue([]),
  fetchRolesByName: vi.fn().mockResolvedValue([]),
}));
vi.mock('@/lib/frappe-sdk', () => ({ call: {}, db: {}, auth: {}, frappe: {} }));

import { Form } from '@/components/ui/form';
import { PermissionsTab } from './PermissionsTab';
import { DESKTOP_ACCESS_FIELDS, type AgentFormValues } from './types';

let formRef: UseFormReturn<AgentFormValues>;

function Harness({ status }: { status: 'loading' | 'ready' | 'error' }) {
  const form = useForm<AgentFormValues>({
    defaultValues: {
      desktop_access_cli: 'allowed',
      desktop_access_files: 'allowed',
      desktop_access_skills: 'allowed',
      desktop_access_local_mcp: 'allowed',
      desktop_access_browser: 'allowed',
      desktop_access_installs: 'allowed',
      desktop_access_processes: 'allowed',
      allow_remote_desktop: false,
      allowed_users: [],
      allowed_roles: [],
    } as unknown as AgentFormValues,
  });
  formRef = form;
  return (
    <MemoryRouter>
      <Form {...form}>
        <PermissionsTab form={form} desktopAccessStatus={status} />
      </Form>
    </MemoryRouter>
  );
}

describe('PermissionsTab desktop access card', () => {
  it('renders the seven capability selectors and the remote switch', () => {
    render(<Harness status="ready" />);
    const card = screen.getByTestId('desktop-access-card');
    for (const { label } of DESKTOP_ACCESS_FIELDS) {
      expect(within(card).getByRole('combobox', { name: label })).toBeInTheDocument();
    }
    expect(DESKTOP_ACCESS_FIELDS).toHaveLength(7);
    expect(within(card).getByRole('switch', { name: 'Allow remote desktop control' })).not.toBeChecked();
  });

  it('writes a chosen level into the form', async () => {
    render(<Harness status="ready" />);
    const card = screen.getByTestId('desktop-access-card');
    const cli = within(card).getByRole('combobox', { name: 'Run commands' });
    // The stand-in renders every field's options in DOM order; the 'Off' option after the CLI trigger is CLI's.
    const options = within(card).getAllByRole('option', { name: 'Off' });
    expect(cli).toBeInTheDocument();
    await userEvent.click(options[0]);
    expect(formRef.getValues('desktop_access_cli')).toBe('off');
    await userEvent.click(within(card).getAllByRole('option', { name: 'Ask' })[1]);
    expect(formRef.getValues('desktop_access_files')).toBe('ask');
    expect(formRef.getValues('desktop_access_skills')).toBe('allowed');
  });

  it('toggles allow_remote_desktop', async () => {
    render(<Harness status="ready" />);
    await userEvent.click(screen.getByRole('switch', { name: 'Allow remote desktop control' }));
    expect(formRef.getValues('allow_remote_desktop')).toBe(true);
  });

  it('is read-only until the stored values have loaded, and says so on failure', () => {
    const { unmount } = render(<Harness status="loading" />);
    expect(screen.getByText(/Loading desktop access/)).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Files' })).toBeDisabled();
    expect(screen.getByRole('switch', { name: 'Allow remote desktop control' })).toBeDisabled();
    unmount();
    render(<Harness status="error" />);
    expect(screen.getByRole('alert')).toHaveTextContent(/could not be loaded/);
    expect(screen.getByRole('combobox', { name: 'Run commands' })).toBeDisabled();
  });
});
