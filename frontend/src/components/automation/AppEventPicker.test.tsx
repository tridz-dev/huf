// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppEventPicker } from './AppEventPicker';
import { TriggerEditor } from './TriggerEditor';
import type { EventAliasSummary } from '@/services/automationApi';

let listImpl: () => Promise<EventAliasSummary[]> = async () => [];
vi.mock('@/services/automationApi', () => ({ listEventAliases: () => listImpl() }));
vi.mock('@/services/agentApi', () => ({ getDocTypes: async () => [] }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const alias = (over: Partial<EventAliasSummary>): EventAliasSummary => ({
  name: 'a',
  app: 'shop',
  key: 'purchase',
  label: 'Customer purchase',
  status: 'Active',
  ...over,
});

function renderPicker(props: Partial<React.ComponentProps<typeof AppEventPicker>> = {}) {
  const onChange = vi.fn();
  const onCustomModeChange = vi.fn();
  render(<AppEventPicker onChange={onChange} onCustomModeChange={onCustomModeChange} {...props} />);
  return { onChange, onCustomModeChange };
}

describe('AppEventPicker', () => {
  beforeEach(() => {
    listImpl = async () => [];
  });

  it('shows a loading placeholder and keeps manual fields hidden until loaded', async () => {
    let resolve!: (rows: EventAliasSummary[]) => void;
    listImpl = () => new Promise((r) => (resolve = r));
    const { onCustomModeChange } = renderPicker();
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(onCustomModeChange).toHaveBeenLastCalledWith(false);
    expect(onCustomModeChange).not.toHaveBeenCalledWith(true);
    resolve([alias({})]);
    await screen.findByLabelText('Business event');
    expect(onCustomModeChange).not.toHaveBeenCalledWith(true);
  });

  it('links the label to the select', async () => {
    listImpl = async () => [alias({})];
    renderPicker();
    expect(await screen.findByLabelText('Business event')).toBeTruthy();
  });

  it('shows a hint with a Desk link when no events exist', async () => {
    listImpl = async () => [];
    const { onCustomModeChange } = renderPicker();
    expect(await screen.findByText(/No business events are set up yet/)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Manage business events' }).getAttribute('href')).toBe(
      '/app/event-alias',
    );
    await waitFor(() => expect(onCustomModeChange).toHaveBeenLastCalledWith(true));
  });

  it('falls back to typed fields with an alert and no Desk link when loading fails', async () => {
    listImpl = () => Promise.reject(new Error('denied'));
    const { onCustomModeChange } = renderPicker();
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByRole('link')).toBeNull();
    await waitFor(() => expect(onCustomModeChange).toHaveBeenLastCalledWith(true));
  });

  it('shows only a neutral note, never a warning, for a reopened custom trigger', async () => {
    listImpl = async () => [alias({})];
    const { onChange } = renderPicker({ appName: 'shop', eventName: 'gone' });
    const note = await screen.findByText(/Custom event/);
    expect(note.getAttribute('role')).toBe('note');
    expect(note.className).not.toContain('text-warning');
    expect(screen.queryByText(/might never fire/)).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('gives the loading placeholder an accessible name', () => {
    listImpl = () => new Promise(() => {});
    renderPicker();
    expect(screen.getByRole('status', { name: 'Business event' })).toBeTruthy();
    expect(screen.getByText('Loading business events')).toBeTruthy();
  });

  it('shows the error alert and typed fields when loading the list rejects', async () => {
    listImpl = () => Promise.reject(new Error('denied'));
    render(
      <TriggerEditor trigger={{ trigger_type: 'App Event' }} onChange={vi.fn()} permissions={{ canEdit: true }} />,
    );
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(await screen.findByText('App name')).toBeTruthy();
  });

  it('hides the manual fields in TriggerEditor while the list is loading', async () => {
    let resolve!: (rows: EventAliasSummary[]) => void;
    listImpl = () => new Promise((r) => (resolve = r));
    render(
      <TriggerEditor trigger={{ trigger_type: 'App Event' }} onChange={vi.fn()} permissions={{ canEdit: true }} />,
    );
    expect(screen.queryByText('App name')).toBeNull();
    resolve([alias({})]);
    await screen.findByLabelText('Business event');
    expect(screen.queryByText('App name')).toBeNull();
  });

  it('offers an explicit switch to the replacement of a deprecated event', async () => {
    listImpl = async () => [
      alias({ name: 'old', key: 'purchase', status: 'Deprecated', replaced_by: 'new' }),
      alias({ name: 'new', key: 'purchase_v2', label: 'Customer purchase v2' }),
    ];
    const { onChange } = renderPicker({ appName: 'shop', eventName: 'purchase' });
    const button = await screen.findByRole('button', { name: 'Switch to Customer purchase v2' });
    expect(onChange).not.toHaveBeenCalled();
    await userEvent.click(button);
    expect(onChange).toHaveBeenCalledWith({ app_name: 'shop', event_name: 'purchase_v2' });
  });

  it('warns without a switch button when a deprecated event has no replacement', async () => {
    listImpl = async () => [alias({ status: 'Deprecated' })];
    renderPicker({ appName: 'shop', eventName: 'purchase' });
    expect(await screen.findByText(/no replacement yet/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Switch to/ })).toBeNull();
  });
});

describe('TriggerEditor App Event draft notice', () => {
  const trigger = { trigger_type: 'App Event' as const };
  beforeEach(() => {
    listImpl = async () => [alias({})];
  });

  it.each([['Draft']])('warns when the automation status is %s', async (status) => {
    render(
      <TriggerEditor trigger={trigger} onChange={vi.fn()} permissions={{ canEdit: true }} automationStatus={status} />,
    );
    expect(await screen.findByText(/This automation is a draft\./)).toBeTruthy();
  });

  it.each([['Paused'], ['Archived']])('warns when the automation status is %s', async (status) => {
    render(
      <TriggerEditor trigger={trigger} onChange={vi.fn()} permissions={{ canEdit: true }} automationStatus={status} />,
    );
    expect(await screen.findByText(new RegExp(`This automation is ${status.toLowerCase()}`))).toBeTruthy();
    expect(screen.queryByText(/is a draft/)).toBeNull();
  });

  it('does not warn while the automation is still loading', async () => {
    render(<TriggerEditor trigger={trigger} onChange={vi.fn()} permissions={{ canEdit: true }} />);
    await screen.findByLabelText('Business event');
    expect(screen.queryByText(/This automation is a draft/)).toBeNull();
  });

  it('does not warn once active', async () => {
    render(
      <TriggerEditor trigger={trigger} onChange={vi.fn()} permissions={{ canEdit: true }} automationStatus="Active" />,
    );
    await screen.findByLabelText('Business event');
    expect(screen.queryByText(/This automation is a draft/)).toBeNull();
  });
});
