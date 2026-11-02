// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

const api = vi.hoisted(() => ({ saveEntryPoint: vi.fn(), deleteEntryPoint: vi.fn() }));
vi.mock('@/services/solutionsApi', async (orig) => ({ ...(await orig<object>()), ...api }));

import { SolutionsApiError } from '@/services/solutionsApi';
import { EntryPointSheet, scopeOptions } from './EntryPointSheet';
import { makeEntry } from './fixtures';

class RO { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;

const gateways = [{ gateway: 'gw1', label: 'Main', phone: '+1' }];

function setup(props: Partial<React.ComponentProps<typeof EntryPointSheet>> = {}) {
  const onSaved = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <EntryPointSheet
      open onOpenChange={onOpenChange} solution="orders" entry={makeEntry()} gateways={gateways}
      gatewayScope="Any number" ceilingFor={() => ({ value: 100, source: 'meta_tier' })} onSaved={onSaved} {...props}
    />,
  );
  return { onSaved, onOpenChange };
}

beforeEach(() => { api.saveEntryPoint.mockReset(); api.deleteEntryPoint.mockReset(); });
afterEach(cleanup);

describe('EntryPointSheet', () => {
  it('caps the slider at the ceiling and shows the lock note', () => {
    setup();
    expect(screen.getByRole('slider')).toHaveAttribute('aria-valuemax', '100');
    expect(screen.getByText('Maximum 100, set on Main')).toBeInTheDocument();
    expect(screen.getByText('Message contains')).toBeInTheDocument();
  });

  it('has no maximum when the number has no limit', () => {
    setup({ ceilingFor: () => ({ value: null, source: 'none' }) });
    expect(screen.queryByRole('slider')).toBeNull();
    expect(screen.queryByText(/Maximum/)).toBeNull();
    expect(screen.getByLabelText('Daily messages it may start', { selector: 'input' })).not.toHaveAttribute('max');
    expect(screen.getByText(/no maximum/i)).toBeInTheDocument();
  });

  it('only offers scopes narrower than or equal to the number scope', () => {
    expect(scopeOptions('Any number')).toEqual(['Only approved contacts', 'Allow list']);
    expect(scopeOptions('Allow-list')).toEqual(['Allow list']);
    expect(scopeOptions('Current contact')).toEqual([]);
  });

  it('saves the edited payload and closes', async () => {
    api.saveEntryPoint.mockResolvedValue(makeEntry());
    const { onSaved, onOpenChange } = setup();
    fireEvent.change(screen.getByLabelText('Daily messages it may start', { selector: 'input' }), { target: { value: '60' } });
    fireEvent.change(screen.getByLabelText('Who it may message'), { target: { value: 'Allow list' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /May message customers first/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.saveEntryPoint).toHaveBeenCalled());
    expect(api.saveEntryPoint).toHaveBeenCalledWith('orders', {
      name: 'ep1', gateway: 'gw1', cap_per_day: 60, scope_override: 'Allow list', allow_first_message: true,
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it.each([
    ['cap_exceeds_ceiling', 'Over the limit.'],
    ['scope_loosening', 'Too wide.'],
  ])('shows the %s error inline and stays open', async (code, message) => {
    api.saveEntryPoint.mockRejectedValue(new SolutionsApiError(code, message));
    const { onSaved } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveAttribute('data-code', code);
    expect(alert).toHaveTextContent(message);
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('creates a keyword entry point', async () => {
    api.saveEntryPoint.mockResolvedValue(makeEntry());
    setup({ entry: null });
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Values'), { target: { value: 'menu, order' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.saveEntryPoint).toHaveBeenCalled());
    expect(api.saveEntryPoint.mock.calls[0][1]).toMatchObject({
      gateway: 'gw1', match_type: 'Keyword', match_values: ['menu', 'order'],
    });
  });

  it('creates a catch-all without values', async () => {
    api.saveEntryPoint.mockResolvedValue(makeEntry());
    setup({ entry: null });
    fireEvent.change(screen.getByLabelText('Match type'), { target: { value: 'Catch-all' } });
    expect(screen.queryByLabelText('Values')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.saveEntryPoint).toHaveBeenCalled());
    expect(api.saveEntryPoint.mock.calls[0][1]).toMatchObject({ match_type: 'Catch-all', match_values: [] });
  });

  it('deletes after confirmation', async () => {
    api.deleteEntryPoint.mockResolvedValue({ success: true });
    const { onSaved } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Delete entry point' }));
    const dialog = await screen.findByRole('alertdialog');
    expect(api.deleteEntryPoint).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.deleteEntryPoint).toHaveBeenCalledWith('ep1'));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
});
