// @vitest-environment jsdom
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { DataGrid } from './DataGrid';
import { FilterChip, SortChip } from './FilterChip';
import { MatchCount } from './GridToolbar';
import { PermissionMatrix, applyGrant, type MatrixCapability, type MatrixValue } from './PermissionMatrix';
import { formatCell, parseCell, parseTsv, type CellValue, type GridColumn } from './types';

type Row = { id: string; name: string; seats: number | null; active: boolean };
const COLS: GridColumn<Row>[] = [
  { key: 'name', label: 'Company', type: 'text', required: true },
  { key: 'seats', label: 'Seats', type: 'number' },
  { key: 'active', label: 'Active', type: 'checkbox' },
];

function Harness({ onChange, initial }: { onChange?: (id: string, k: string, v: CellValue) => string | void; initial?: Row[] }) {
  const [rows, setRows] = useState<Row[]>(initial ?? [
    { id: 'a', name: 'Acme', seats: 1, active: true },
    { id: 'b', name: 'Bright', seats: 2, active: false },
  ]);
  return (
    <DataGrid<Row> label="Customers" columns={COLS} rows={rows} getRowId={(r) => r.id}
      onCellChange={(id, k, v) => {
        const msg = onChange?.(id, k, v);
        if (msg) return msg;
        setRows((rs) => rs.map((r) => (r.id === id ? { ...r, [k]: v } : r)));
      }} />
  );
}

const cell = (r: number, c: number) => document.querySelector(`[data-cell="${r}:${c}"]`) as HTMLElement;

describe('DataGrid keyboard editing', () => {
  it('types to edit, Enter commits and moves down', async () => {
    const spy = vi.fn();
    render(<Harness onChange={spy} />);
    await userEvent.click(cell(0, 0));
    await userEvent.keyboard('Z');
    const input = screen.getByRole('textbox', { name: 'Company' });
    expect(input).toHaveValue('Z');
    await userEvent.keyboard('eta{Enter}');
    expect(spy).toHaveBeenCalledWith('a', 'name', 'Zeta');
    expect(cell(0, 0)).toHaveTextContent('Zeta');
    expect(cell(1, 0)).toHaveFocus();
  });

  it('Tab commits and moves right; numbers are parsed', async () => {
    const spy = vi.fn();
    render(<Harness onChange={spy} />);
    await userEvent.click(cell(0, 1));
    await userEvent.keyboard('{Enter}');
    const input = screen.getByRole('textbox', { name: 'Seats' });
    await userEvent.clear(input);
    await userEvent.type(input, '1,200{Tab}');
    expect(spy).toHaveBeenCalledWith('a', 'seats', 1200);
    expect(cell(0, 1)).toHaveTextContent('1,200');
    expect(cell(0, 2)).toHaveFocus();
  });

  it('Esc restores the old value', async () => {
    const spy = vi.fn();
    render(<Harness onChange={spy} />);
    await userEvent.click(cell(1, 0));
    await userEvent.keyboard('X{Escape}');
    expect(spy).not.toHaveBeenCalled();
    expect(cell(1, 0)).toHaveTextContent('Bright');
    expect(cell(1, 0)).toHaveFocus();
  });

  it('shows a fix hint for an invalid value and keeps the editor open', async () => {
    render(<Harness />);
    await userEvent.click(cell(0, 1));
    await userEvent.keyboard('abc{Enter}');
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a number');
    expect(cell(0, 1)).toHaveAttribute('aria-invalid', 'true');
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('alert')).toBeNull();
    expect(cell(0, 1)).toHaveTextContent('1');
  });

  it('shows a rejection message from onCellChange', async () => {
    render(<Harness onChange={() => 'That name is taken'} />);
    await userEvent.click(cell(0, 0));
    await userEvent.keyboard('Q{Enter}');
    expect(screen.getByRole('alert')).toHaveTextContent('That name is taken');
  });

  it('arrows move the active cell; Space toggles a checkbox', async () => {
    const spy = vi.fn();
    render(<Harness onChange={spy} />);
    await userEvent.click(cell(0, 0));
    await userEvent.keyboard('{ArrowRight}{ArrowRight}');
    expect(cell(0, 2)).toHaveFocus();
    await userEvent.keyboard(' ');
    expect(spy).toHaveBeenCalledWith('a', 'active', false);
  });

  it('windows large row counts', () => {
    const many = Array.from({ length: 2000 }, (_, i) => ({ id: String(i), name: `R${i}`, seats: i, active: false }));
    render(<Harness initial={many} />);
    expect(document.querySelectorAll('tbody tr[aria-rowindex]').length).toBeLessThan(200);
  });
});

describe('FilterChip / SortChip / MatchCount', () => {
  it('reads as a sentence and removes by button or Backspace', async () => {
    const onRemove = vi.fn();
    render(<FilterChip field="Status" operator="is" value="Active" onRemove={onRemove} />);
    expect(screen.getByTestId('filter-chip')).toHaveTextContent('StatusisActive');
    await userEvent.click(screen.getByRole('button', { name: 'Remove filter Status is Active' }));
    screen.getByRole('button', { name: 'Filter: Status is Active' }).focus();
    await userEvent.keyboard('{Backspace}');
    expect(onRemove).toHaveBeenCalledTimes(2);
  });

  it('opens its editor popover', async () => {
    render(<FilterChip field="Seats" operator="is more than" value="3" onRemove={() => {}} editor={<p>Edit me</p>} />);
    await userEvent.click(screen.getByRole('button', { name: 'Filter: Seats is more than 3' }));
    expect(await screen.findByText('Edit me')).toBeInTheDocument();
  });

  it('sort chip reverses and removes', async () => {
    const onToggle = vi.fn();
    const onRemove = vi.fn();
    render(<SortChip field="Renewal" direction="asc" directionLabel="Oldest first" onToggle={onToggle} onRemove={onRemove} />);
    await userEvent.click(screen.getByRole('button', { name: /Sorted by Renewal, Oldest first/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Remove sort by Renewal' }));
    expect(onToggle).toHaveBeenCalledOnce();
    expect(onRemove).toHaveBeenCalledOnce();
  });

  it('match count says "N of M" only while filtered', () => {
    const { rerender } = render(<MatchCount shown={212} total={1284} />);
    expect(screen.getByRole('status')).toHaveTextContent('212 of 1,284 rows');
    rerender(<MatchCount shown={1284} total={1284} />);
    expect(screen.getByRole('status')).toHaveTextContent('1,284 rows');
  });
});

describe('PermissionMatrix', () => {
  const CAPS: MatrixCapability[] = [
    { key: 'read', label: 'Read' },
    { key: 'create', label: 'Create', implies: ['read'] },
    { key: 'edit', label: 'Edit', implies: ['read'] },
    { key: 'delete', label: 'Delete', implies: ['edit'] },
  ];

  it('applyGrant closes over implications both ways', () => {
    expect(applyGrant(CAPS, {}, 'delete', true)).toEqual({ delete: true, edit: true, read: true });
    expect(applyGrant(CAPS, { read: true, edit: true, delete: true, create: true }, 'read', false)).toEqual({ read: false, edit: false, delete: false, create: false });
  });

  it('toggles a cell with implications and supports arrow keys', async () => {
    function H() {
      const [v, setV] = useState<MatrixValue>({});
      return <PermissionMatrix label="Access" subjects={[{ id: 's1', label: 'Billing' }, { id: 's2', label: 'Support' }]} capabilities={CAPS} value={v} onChange={(n) => setV(n)} />;
    }
    render(<H />);
    await userEvent.click(screen.getByRole('checkbox', { name: 'Edit for Billing' }));
    expect(screen.getByRole('checkbox', { name: 'Read for Billing' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Read for Support' })).not.toBeChecked();
    await userEvent.keyboard('{ArrowDown}');
    expect(screen.getByRole('checkbox', { name: 'Edit for Support' })).toHaveFocus();
    const row = screen.getByRole('row', { name: /Support/ });
    expect(within(row).getAllByRole('checkbox')).toHaveLength(4);
  });
});

describe('cell vocabulary', () => {
  it('formats and parses', () => {
    expect(formatCell({ type: 'currency' }, 1200)).toBe((1200).toLocaleString(undefined, { minimumFractionDigits: 2 }));
    expect(formatCell({ type: 'select', options: [{ value: 'a', label: 'Active' }] }, 'a')).toBe('Active');
    expect(parseCell('number', '1,200.5')).toEqual({ value: 1200.5 });
    expect(parseCell('date', 'nope')).toHaveProperty('error');
    expect(parseTsv('a\tb\r\nc\td\n')).toEqual([['a', 'b'], ['c', 'd']]);
  });
});

describe('DataGrid Shift-range selection (DSF-1)', () => {
  type R = { id: string; name: string };
  const cols: GridColumn<R>[] = [{ key: 'name', label: 'Name', type: 'text' }];
  const mk = (ids: string[]) => ids.map((id) => ({ id, name: id.toUpperCase() }));
  function Sel({ onSel }: { onSel: (s: Set<string>) => void }) {
    const [rows, setRows] = useState(mk(['a', 'b', 'c', 'd', 'e', 'f']));
    const [sel, setSel] = useState(new Set<string>());
    return (
      <>
        <button onClick={() => setRows(mk(['x', 'y', 'z']))}>Next page</button>
        <button onClick={() => setRows((rs) => [...rs].reverse())}>Sort</button>
        <DataGrid<R> label="T" columns={cols} rows={rows} getRowId={(r) => r.id} selected={sel}
          onSelectedChange={(s) => { setSel(s); onSel(s); }} onCellChange={() => {}} />
      </>
    );
  }
  const shiftClick = async (name: string) => {
    const u = userEvent.setup();
    await u.keyboard('{Shift>}');
    await u.click(screen.getByRole('checkbox', { name }));
    await u.keyboard('{/Shift}');
  };

  it('does not crash when the anchor index is past the new row set', async () => {
    const onSel = vi.fn();
    render(<Sel onSel={onSel} />);
    await userEvent.click(screen.getByRole('checkbox', { name: 'Select row 6' }));
    await userEvent.click(screen.getByRole('button', { name: 'Next page' }));
    await shiftClick('Select row 2');
    expect([...onSel.mock.lastCall![0]].sort()).toEqual(['f', 'y']);
  });

  it('selects the right range after the rows change', async () => {
    const onSel = vi.fn();
    render(<Sel onSel={onSel} />);
    await userEvent.click(screen.getByRole('checkbox', { name: 'Select row 2' })); // b
    await userEvent.click(screen.getByRole('button', { name: 'Sort' })); // f e d c b a
    await userEvent.click(screen.getByRole('checkbox', { name: 'Select row 1' })); // f, new anchor
    await shiftClick('Select row 3'); // f..d
    expect([...onSel.mock.lastCall![0]].sort()).toEqual(['b', 'd', 'e', 'f']);
  });
});
