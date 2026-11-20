/**
 * DataGrid (DESIGN.md §6.11): an editable, typed spreadsheet-like grid.
 * Click or type to edit, Tab/Enter/Esc like a spreadsheet, row checkboxes
 * with Shift-click ranges, an add-row line, and windowed rendering for
 * large row counts. Domain-free: rows are opaque, columns describe types.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Plus } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { ShortcutKey } from '@/components/ui/shortcut-key';
import { cn } from '@/lib/utils';
import { CellDisplay, CellEditor } from './GridCell';
import { useGridNav, type CellPos, type CommitResult } from './useGridNav';
import { TYPE_ICON, TYPE_LABEL, WIDTH_CLASS, cellValue, isNumeric, type CellValue, type GridColumn } from './types';

/** Row height in px; matches `h-9` on rows so windowing math stays exact. */
export const GRID_ROW_H = 36;

export interface DataGridProps<R> {
  columns: GridColumn<R>[];
  rows: R[];
  getRowId: (row: R) => string;
  /** Accessible name, e.g. "Customers". */
  label: string;
  /** Persist one cell. Return / resolve a one-line message (or throw) to reject it. */
  onCellChange?: (rowId: string, key: string, value: CellValue) => CommitResult;
  selected?: ReadonlySet<string>;
  onSelectedChange?: (next: Set<string>) => void;
  onAddRow?: () => void;
  onOpenRow?: (rowId: string) => void;
  /** Spreadsheet paste (tab-separated) starting at the active cell. */
  onPaste?: (matrix: string[][], at: { rowId: string | null; key: string }) => void;
  /** Row number offset when the grid shows a page (start index). */
  rowNumberOffset?: number;
  /** Window rendering above this many rows. */
  windowFrom?: number;
  /** Shown in place of the body when there are no rows. */
  empty?: ReactNode;
  className?: string;
}

const OVERSCAN = 8;

export function DataGrid<R>({
  columns, rows, getRowId, label, onCellChange, selected, onSelectedChange, onAddRow, onOpenRow, onPaste,
  rowNumberOffset = 0, windowFrom = 100, empty, className,
}: DataGridProps<R>) {
  const nav = useGridNav<R>({
    columns,
    rows,
    commit: (r, c, v) => onCellChange?.(getRowId(rows[r]), columns[c].key, v),
    onOpenRow: onOpenRow ? (r) => onOpenRow(getRowId(rows[r])) : undefined,
    onPaste: onPaste ? (m, at) => onPaste(m, { rowId: rows[at.r] ? getRowId(rows[at.r]) : null, key: columns[at.c].key }) : undefined,
  });
  const scroller = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLTableSectionElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewH, setViewH] = useState(600);
  const anchor = useRef<number | null>(null);
  const wasEditing = useRef(false);
  const uid = useRef(`grid-${Math.random().toString(36).slice(2, 8)}`).current;

  const windowed = rows.length > windowFrom;
  const first = windowed ? Math.max(0, Math.floor(scrollTop / GRID_ROW_H) - OVERSCAN) : 0;
  const last = windowed ? Math.min(rows.length, Math.ceil((scrollTop + viewH) / GRID_ROW_H) + OVERSCAN) : rows.length;

  useEffect(() => {
    const el = scroller.current;
    if (el?.clientHeight) setViewH(el.clientHeight);
  }, []);

  // Keep the active cell in view and focused while focus is inside the grid.
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    if (windowed) {
      const top = nav.active.r * GRID_ROW_H;
      if (top < el.scrollTop) el.scrollTop = top;
      else if (top + GRID_ROW_H > el.scrollTop + el.clientHeight) el.scrollTop = top + GRID_ROW_H - el.clientHeight;
    }
    const act = document.activeElement;
    const lostToBody = wasEditing.current && (!act || act === document.body);
    wasEditing.current = nav.editing;
    if (!nav.editing && (el.contains(act) || lostToBody)) {
      body.current?.querySelector<HTMLElement>(`[data-cell="${nav.active.r}:${nav.active.c}"]`)?.focus();
    }
  }, [nav.active, nav.editing, windowed]);

  const selectable = Boolean(onSelectedChange);
  const sel = selected ?? new Set<string>();
  const allOn = rows.length > 0 && rows.every((r) => sel.has(getRowId(r)));
  const someOn = !allOn && rows.some((r) => sel.has(getRowId(r)));

  const toggleRow = (i: number, shift: boolean) => {
    const next = new Set(sel);
    const id = getRowId(rows[i]);
    const on = !sel.has(id);
    if (shift && anchor.current !== null) {
      const [a, b] = [Math.min(anchor.current, i), Math.max(anchor.current, i)];
      for (let k = a; k <= b; k++) (on ? next.add(getRowId(rows[k])) : next.delete(getRowId(rows[k])));
    } else on ? next.add(id) : next.delete(id);
    anchor.current = i;
    onSelectedChange?.(next);
  };

  const errId = `${uid}-err`;
  const lead = selectable ? 2 : 1;

  return (
    <div
      ref={scroller}
      onScroll={(e) => windowed && setScrollTop(e.currentTarget.scrollTop)}
      className={cn('relative max-h-[70vh] overflow-auto rounded-lg border border-line bg-panel', className)}
    >
      <table role="grid" aria-label={label} aria-rowcount={rows.length + 1} aria-colcount={columns.length + lead}
        className="w-full border-separate border-spacing-0 text-ui-text" onKeyDown={nav.onGridKeyDown} onPaste={nav.onGridPaste}>
        <thead className="sticky top-0 z-10 bg-paper-deep">
          <tr aria-rowindex={1}>
            {selectable && (
              <th scope="col" className="w-10 border-b border-line px-3 text-left">
                <Checkbox aria-label="Select all rows" checked={allOn ? true : someOn ? 'indeterminate' : false}
                  onCheckedChange={(v) => onSelectedChange?.(v === true ? new Set(rows.map(getRowId)) : new Set())} />
              </th>
            )}
            <th scope="col" className="w-12 border-b border-line px-2 text-right text-meta font-normal text-steel-soft">
              <span className="sr-only">Row</span>
            </th>
            {columns.map((col) => {
              const Icon = TYPE_ICON[col.type];
              return (
                <th key={col.key} scope="col" title={TYPE_LABEL[col.type]}
                  className={cn('h-9 border-b border-l border-line px-3 text-left text-micro font-medium text-steel', col.width && WIDTH_CLASS[col.width])}>
                  <span className={cn('flex items-center gap-1.5', isNumeric(col.type) && 'justify-end')}>
                    <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-steel-soft" />
                    <span className="truncate">{col.label}</span>
                    <span className="sr-only">, {TYPE_LABEL[col.type]}</span>
                    {col.required && <span aria-label="required" className="text-destructive">*</span>}
                    {col.tag && <span className="text-meta font-normal text-steel-soft">{col.tag}</span>}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody ref={body}>
          {rows.length === 0 && empty ? (
            <tr><td colSpan={columns.length + lead} className="p-8 text-center text-steel">{empty}</td></tr>
          ) : null}
          {first > 0 && <tr aria-hidden="true"><td colSpan={columns.length + lead} height={first * GRID_ROW_H} /></tr>}
          {rows.slice(first, last).map((row, k) => {
            const r = first + k;
            const id = getRowId(row);
            const isSel = sel.has(id);
            return (
              <tr key={id} aria-rowindex={r + 2} aria-selected={selectable ? isSel : undefined}
                className={cn('group h-9', isSel ? 'bg-signal/5' : 'hover:bg-paper-deep/60')}>
                {selectable && (
                  <td className="border-b border-line px-3">
                    <Checkbox aria-label={`Select row ${r + 1 + rowNumberOffset}`} checked={isSel}
                      onClick={(e) => { e.preventDefault(); toggleRow(r, e.shiftKey); }} />
                  </td>
                )}
                <td className="border-b border-line px-2 text-right font-mono text-meta text-steel-soft">
                  {onOpenRow ? (
                    <button type="button" onClick={() => onOpenRow(id)} aria-label={`Open row ${r + 1 + rowNumberOffset}`}
                      className="rounded px-1 hover:bg-paper-deep hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                      {r + 1 + rowNumberOffset}
                    </button>
                  ) : r + 1 + rowNumberOffset}
                </td>
                {columns.map((col, c) => {
                  const isActive = nav.active.r === r && nav.active.c === c;
                  const isEditing = isActive && nav.editing;
                  const err = nav.error && nav.error.r === r && nav.error.c === c ? nav.error.message : null;
                  return (
                    <td key={col.key} role="gridcell" data-cell={`${r}:${c}`} tabIndex={isActive && !isEditing ? 0 : -1}
                      aria-readonly={col.readOnly || undefined} aria-invalid={err ? true : undefined}
                      onClick={() => nav.setActive({ r, c } as CellPos)}
                      onDoubleClick={() => nav.startEdit({ r, c })}
                      className={cn(
                        'relative max-w-0 border-b border-l border-line px-3 outline-none',
                        isEditing ? 'p-0' : 'cursor-cell',
                        isActive && 'ring-2 ring-inset ring-signal',
                        err && 'bg-destructive-tint ring-destructive',
                        col.width && WIDTH_CLASS[col.width],
                      )}>
                      {isEditing ? (
                        <CellEditor col={col} draft={nav.draft} onDraft={nav.setDraft} invalid={Boolean(err)} describedBy={err ? errId : undefined}
                          onCommit={(dir, v) => void nav.finish(dir, v)} onCancel={nav.cancel} />
                      ) : (
                        <CellDisplay col={col} value={cellValue(col, row)} onToggle={onCellChange ? () => nav.toggle({ r, c }) : undefined} />
                      )}
                      {err && (
                        <p id={errId} role="alert" className="absolute left-0 top-full z-20 mt-0.5 w-max max-w-xs rounded-md border border-destructive/30 bg-panel px-2 py-1 text-micro text-destructive shadow-md">
                          {err} <span className="text-steel">· Esc to undo</span>
                        </p>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
          {last < rows.length && <tr aria-hidden="true"><td colSpan={columns.length + lead} height={(rows.length - last) * GRID_ROW_H} /></tr>}
          {onAddRow && (
            <tr className="h-9">
              <td colSpan={columns.length + lead} className="border-b border-line px-3">
                <button type="button" onClick={onAddRow}
                  className="inline-flex items-center gap-2 rounded text-ui-text text-steel hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <Plus aria-hidden="true" className="h-3.5 w-3.5" /> Add row
                  <ShortcutKey size="sm" keys={['⌘', 'Enter']} />
                </button>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
