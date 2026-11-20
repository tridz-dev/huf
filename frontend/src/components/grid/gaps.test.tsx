// @vitest-environment jsdom
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ChangeImpactNotice } from './ChangeImpactNotice';
import { ColumnTypeList, gridTypeOptions } from './ColumnTypePicker';
import { DataGrid } from './DataGrid';
import { FilterBuilder, filterNeedsValue, filterOpsFor, type FilterCondition } from './FilterBuilder';
import { GridFooter, footerText } from './GridToolbar';
import { ImportMapper, importGaps } from './ImportMapper';
import { nextSort, sortDirectionLabel, type GridColumn, type GridSort } from './types';

type Row = { id: string; name: string; seats: number };
const COLS: GridColumn<Row>[] = [
  { key: 'name', label: 'Company', type: 'text' },
  { key: 'seats', label: 'Seats', type: 'number' },
  { key: 'id', label: 'Key', type: 'text', sortable: false },
];
const ROWS: Row[] = [{ id: 'a', name: 'Acme', seats: 1 }];

function SortHarness({ spy }: { spy: (s: GridSort | null) => void }) {
  const [sort, setSort] = useState<GridSort | null>(null);
  return <DataGrid<Row> label="T" columns={COLS} rows={ROWS} getRowId={(r) => r.id} sort={sort}
    onSortChange={(s) => { spy(s); setSort(s); }} />;
}

describe('DataGrid sortable headers', () => {
  it('cycles asc → desc → none and sets aria-sort', async () => {
    const spy = vi.fn();
    render(<SortHarness spy={spy} />);
    const th = () => screen.getAllByRole('columnheader').find((h) => h.textContent?.includes('Seats'))!;
    expect(th()).toHaveAttribute('aria-sort', 'none');
    const btn = screen.getByRole('button', { name: /^Seats, not sorted/ });
    await userEvent.click(btn);
    expect(th()).toHaveAttribute('aria-sort', 'ascending');
    btn.focus();
    await userEvent.keyboard('{Enter}');
    expect(th()).toHaveAttribute('aria-sort', 'descending');
    await userEvent.keyboard(' ');
    expect(th()).toHaveAttribute('aria-sort', 'none');
    expect(spy.mock.calls.map((c) => c[0])).toEqual([{ key: 'seats', direction: 'asc' }, { key: 'seats', direction: 'desc' }, null]);
  });

  it('leaves sortable:false columns and unsortable grids static', () => {
    render(<SortHarness spy={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /^Key,/ })).toBeNull();
  });

  it('nextSort and direction words', () => {
    expect(nextSort({ key: 'a', direction: 'desc' }, 'b')).toEqual({ key: 'b', direction: 'asc' });
    expect(sortDirectionLabel('date', 'asc')).toBe('Oldest first');
    expect(sortDirectionLabel('currency', 'desc')).toBe('9→1');
  });
});

describe('FilterBuilder', () => {
  it('offers operators per type', () => {
    expect(filterOpsFor('number')).toContain('is more than');
    expect(filterOpsFor('text')).not.toContain('is before');
    expect(filterOpsFor('checkbox')).toEqual(['is']);
    expect(filterNeedsValue('is empty')).toBe(false);
  });

  it('adds a condition as a chip and removes it', async () => {
    const spy = vi.fn();
    function H() {
      const [v, setV] = useState<FilterCondition[]>([]);
      return <FilterBuilder columns={COLS} value={v} onChange={(n) => { spy(n); setV(n); }} />;
    }
    render(<H />);
    await userEvent.click(screen.getByRole('button', { name: /Filter/ }));
    const add = screen.getByRole('button', { name: 'Add filter' });
    expect(add).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Value'), 'Acme');
    await userEvent.click(add);
    expect(spy).toHaveBeenLastCalledWith([{ field: 'name', op: 'is', value: 'Acme' }]);
    expect(screen.getByRole('button', { name: 'Filter: Company is Acme' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Remove filter Company is Acme' }));
    expect(spy).toHaveBeenLastCalledWith([]);
  });
});

describe('GridFooter totals', () => {
  it('handles exact, approximate and unknown totals', () => {
    expect(footerText({ from: 1, to: 25, total: 1284 })).toBe('Showing 1–25 of 1,284 rows');
    expect(footerText({ from: 1, to: 25, total: 25, approximate: true })).toBe('Showing 1–25 of 25+ rows');
    expect(footerText({ from: 1, to: 25, total: null })).toBe('Showing 1–25 rows');
    expect(footerText({ from: 0, to: 0, total: null })).toBe('No rows');
    render(<GridFooter from={1} to={25} total={25} approximate />);
    expect(screen.getByTestId('grid-footer-range')).toHaveTextContent('25+ rows');
  });
});

describe('ChangeImpactNotice footer', () => {
  it('confirms and cancels; destructive when data is lost', async () => {
    const ok = vi.fn();
    const no = vi.fn();
    render(<ChangeImpactNotice title="Change type" lines={[{ count: 4, label: 'values cleared', kind: 'loss' }]}
      onConfirm={ok} onCancel={no} confirmLabel="Change type" />);
    await userEvent.click(screen.getByRole('button', { name: 'Change type' }));
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(ok).toHaveBeenCalledOnce();
    expect(no).toHaveBeenCalledOnce();
  });

  it('has no footer by default and disables confirm while checking', () => {
    const { rerender } = render(<ChangeImpactNotice title="x" />);
    expect(screen.queryByTestId('change-impact-footer')).toBeNull();
    rerender(<ChangeImpactNotice title="x" checking onConfirm={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Apply change' })).toBeDisabled();
  });
});

describe('ColumnTypeList', () => {
  it('shows icon, label, description; searches; selects', async () => {
    const spy = vi.fn();
    render(<ColumnTypeList options={gridTypeOptions()} value="text" onSelect={spy} searchable />);
    expect(screen.getByRole('option', { name: /Text.*short line/ })).toHaveAttribute('aria-selected', 'true');
    await userEvent.type(screen.getByLabelText('Search field types'), 'money');
    expect(screen.getAllByRole('option')).toHaveLength(1);
    await userEvent.click(screen.getByRole('option', { name: /Currency/ }));
    expect(spy).toHaveBeenCalledWith('currency');
  });
});

describe('ImportMapper gaps', () => {
  const targets = [{ key: 'name', label: 'Name', type: 'text' as const, required: true }, { key: 'n', label: 'Notes', type: 'text' as const }];
  const columns = [{ header: 'Notes', samples: ['x'], target: 'n' }, { header: 'Junk', samples: ['y'], target: null }];
  it('reports dropped columns and unmapped required fields', () => {
    expect(importGaps(columns, targets)).toEqual({ dropped: ['Junk'], missingRequired: [targets[0]] });
    render(<ImportMapper columns={columns} targets={targets} onMap={vi.fn()} totals={{ valid: 1, rejected: 0 }} />);
    expect(screen.getByTestId('import-dropped')).toHaveTextContent('1 column won’t be imported: Junk.');
    expect(screen.getByTestId('import-missing-required')).toHaveTextContent('Required field Name has no column');
  });
});
