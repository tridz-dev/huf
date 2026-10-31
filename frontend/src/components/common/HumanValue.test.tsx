// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const copied = vi.fn<(text: string) => Promise<boolean>>(async () => true);
vi.mock('@/lib/clipboard', () => ({ copyText: (t: string) => copied(t) }));

import { HumanValue } from './HumanValue';

const order = { customer_name: 'Ada Lovelace', total: 450, paid: false, note: null, created_at: '2026-10-29T17:15:54Z', lines: [{ name: 'Widget', qty: 2 }, { name: 'Gadget', qty: 1 }], address: { city: 'London', zip: '' } };

describe('HumanValue', () => {
  it('shows labelled rows and no JSON by default', () => {
    render(<HumanValue value={order} raw />);
    expect(screen.getByTestId('flow-human-label-customer_name')).toHaveTextContent('Customer Name');
    expect(screen.getByTestId('flow-human-value-customer_name')).toHaveTextContent('Ada Lovelace');
    expect(screen.getByTestId('flow-human-value-paid')).toHaveTextContent('No');
    expect(screen.queryByTestId('flow-human-row-note')).toBeNull();
    expect(screen.getByTestId('flow-human-value-created_at').textContent).not.toMatch(/2026-10-29T|Z$/);
    const text = screen.getByTestId('flow-human-rows').textContent ?? '';
    expect(text).not.toMatch(/[{}"]|null/);
  });

  it('lists read "N items" and open to one card per item', () => {
    render(<HumanValue value={order} />);
    expect(screen.getByTestId('flow-human-list-lines-count')).toHaveTextContent('2 items');
    expect(screen.queryByTestId('flow-human-list-lines-items')).toBeNull();
    fireEvent.click(screen.getByTestId('flow-human-list-lines-toggle'));
    expect(screen.getByTestId('flow-human-list-lines-item-0')).toHaveTextContent('Widget');
    expect(screen.getByTestId('flow-human-list-lines-item-1')).toHaveTextContent('Gadget');
  });

  it('Raw opens the exact data and hides again', () => {
    render(<HumanValue value={{ amount: 7, note: null }} raw rawTextTestId="the-raw" />);
    expect(screen.queryByTestId('the-raw')).toBeNull();
    fireEvent.click(screen.getByTestId('flow-human-raw-toggle'));
    expect(screen.getByTestId('the-raw').textContent).toContain('"note": null');
    fireEvent.click(screen.getByTestId('flow-human-raw-toggle'));
    expect(screen.queryByTestId('the-raw')).toBeNull();
  });

  it('shows the given text when there is nothing to show', () => {
    render(<HumanValue value={{ a: null }} emptyText="No data was sent." />);
    expect(screen.getByTestId('flow-human-empty')).toHaveTextContent('No data was sent.');
  });

  it('folds long text behind Show more', () => {
    render(<HumanValue value={{ body: 'lorem '.repeat(80) }} />);
    const more = screen.getByTestId('flow-human-text-body-more');
    expect(screen.getByTestId('flow-human-text-body').textContent!.length).toBeLessThan(140);
    fireEvent.click(more);
    expect(screen.getByTestId('flow-human-text-body').textContent!.length).toBeGreaterThan(300);
  });

  it('resolves step ids to titles', () => {
    render(<HumanValue value={{ chose: 'node_1793273127004' }} names={{ node_1793273127004: 'Approved' }} />);
    expect(screen.getByTestId('flow-human-value-chose')).toHaveTextContent('Approved');
  });

  it('shows step names in the raw view, says so, and Copy still gives the original ids', async () => {
    render(<HumanValue value={{ chosen: 'Send the email' }} raw rawValue={{ node_id: 'Send the email' }} rawCopyValue={{ node_id: 'n2' }} />);
    fireEvent.click(screen.getByTestId('flow-human-raw-toggle'));
    expect(screen.getByTestId('flow-json-flow-human-raw-text')).toHaveTextContent('Send the email');
    expect(screen.getByTestId('flow-json-flow-human-raw-help')).toHaveTextContent('Step names are shown in place of internal ids');
    fireEvent.click(screen.getByTestId('flow-json-flow-human-raw-copy'));
    await waitFor(() => expect(copied).toHaveBeenCalledWith(JSON.stringify({ node_id: 'n2' }, null, 2)));
  });

  it('keeps the usual help when nothing was renamed', () => {
    render(<HumanValue value={order} raw rawCopyValue={order} />);
    fireEvent.click(screen.getByTestId('flow-human-raw-toggle'));
    expect(screen.getByTestId('flow-json-flow-human-raw-help')).toHaveTextContent('The exact data, as it was recorded');
  });
});
