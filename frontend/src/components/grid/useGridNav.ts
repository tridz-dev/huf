/**
 * Keyboard model of the DataGrid (DESIGN.md §6.11.4): one active cell,
 * a navigate mode and an edit mode. Kept out of the view so other grid-like
 * surfaces (a matrix, a mapper) can reuse the same muscle memory.
 */
import { useCallback, useRef, useState, type ClipboardEvent, type KeyboardEvent } from 'react';
import { cellValue, parseCell, parseTsv, type CellValue, type GridColumn } from './types';

export interface CellPos {
  r: number;
  c: number;
}

export type CommitResult = void | string | null | Promise<void | string | null>;

interface Options<R> {
  columns: GridColumn<R>[];
  rows: R[];
  /** Persist a value. Return / resolve a message (or throw) to reject it. */
  commit: (r: number, c: number, value: CellValue) => CommitResult;
  onPaste?: (matrix: string[][], at: CellPos) => void;
  onOpenRow?: (r: number) => void;
}

const MOVES: Record<string, [number, number]> = {
  ArrowDown: [1, 0],
  ArrowUp: [-1, 0],
  ArrowRight: [0, 1],
  ArrowLeft: [0, -1],
};

export function useGridNav<R>({ columns, rows, commit, onPaste, onOpenRow }: Options<R>) {
  const [active, setActive] = useState<CellPos>({ r: 0, c: 0 });
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<(CellPos & { message: string }) | null>(null);
  const busy = useRef(false);

  const clamp = useCallback(
    (p: CellPos): CellPos => ({
      r: Math.max(0, Math.min(rows.length - 1, p.r)),
      c: Math.max(0, Math.min(columns.length - 1, p.c)),
    }),
    [rows.length, columns.length],
  );

  const raw = (p: CellPos) => {
    const v = cellValue(columns[p.c], rows[p.r]);
    return v === null || v === undefined ? '' : String(v);
  };

  const startEdit = (p: CellPos = active, seed?: string) => {
    const col = columns[p.c];
    if (!col || col.readOnly || col.type === 'checkbox' || !rows[p.r]) return;
    setActive(p);
    setError(null);
    setDraft(seed ?? raw(p));
    setEditing(true);
  };

  const cancel = () => {
    setEditing(false);
    setError(null);
  };

  const step = (dir: 'down' | 'right' | 'left' | 'none') => {
    setActive((a) => {
      if (dir === 'down') return clamp({ r: a.r + 1, c: a.c });
      if (dir === 'right') return a.c === columns.length - 1 ? clamp({ r: a.r + 1, c: 0 }) : { r: a.r, c: a.c + 1 };
      if (dir === 'left') return a.c === 0 ? clamp({ r: a.r - 1, c: columns.length - 1 }) : { r: a.r, c: a.c - 1 };
      return a;
    });
  };

  const finish = async (dir: 'down' | 'right' | 'left' | 'none', text: string = draft) => {
    if (!editing || busy.current) return;
    const { r, c } = active;
    const col = columns[c];
    const fail = (message: string) => setError({ r, c, message });
    if (text === raw(active)) {
      cancel();
      step(dir);
      return;
    }
    const parsed = parseCell(col.type, text);
    if ('error' in parsed) return fail(parsed.error);
    if (col.required && parsed.value === null) return fail(`${col.label} can't be empty`);
    const invalid = col.validate?.(parsed.value, rows[r]);
    if (invalid) return fail(invalid);
    busy.current = true;
    try {
      const msg = await commit(r, c, parsed.value);
      if (msg) return fail(msg);
    } catch (e) {
      return fail(e instanceof Error && e.message ? e.message.split('\n')[0] : "Couldn't save this value");
    } finally {
      busy.current = false;
    }
    cancel();
    step(dir);
  };

  const toggle = (p: CellPos) => {
    const col = columns[p.c];
    if (col.type !== 'checkbox' || col.readOnly) return;
    void commit(p.r, p.c, !cellValue(col, rows[p.r]));
  };

  /** Keys on the grid while no editor is open. */
  const onGridKeyDown = (e: KeyboardEvent) => {
    if (editing || rows.length === 0) return;
    const mod = e.metaKey || e.ctrlKey;
    if (MOVES[e.key]) {
      e.preventDefault();
      const [dr, dc] = MOVES[e.key];
      setActive((a) => clamp(mod ? { r: dr ? (dr > 0 ? rows.length - 1 : 0) : a.r, c: dc ? (dc > 0 ? columns.length - 1 : 0) : a.c } : { r: a.r + dr, c: a.c + dc }));
    } else if (e.key === 'Tab') {
      const edge = e.shiftKey ? active.r === 0 && active.c === 0 : active.r === rows.length - 1 && active.c === columns.length - 1;
      if (edge) return; // let focus leave the grid
      e.preventDefault();
      step(e.shiftKey ? 'left' : 'right');
    } else if (e.key === 'Enter' || e.key === 'F2') {
      e.preventDefault();
      if (e.key === 'Enter' && e.shiftKey && onOpenRow) onOpenRow(active.r);
      else if (columns[active.c]?.type === 'checkbox') toggle(active);
      else startEdit();
    } else if (e.key === ' ' && columns[active.c]?.type === 'checkbox') {
      e.preventDefault();
      toggle(active);
    } else if ((e.key === 'Backspace' || e.key === 'Delete') && !columns[active.c]?.readOnly) {
      e.preventDefault();
      startEdit(active, '');
    } else if (e.key.length === 1 && !mod && !e.altKey) {
      e.preventDefault();
      startEdit(active, e.key);
    }
  };

  const onGridPaste = (e: ClipboardEvent) => {
    if (editing || !onPaste) return;
    const text = e.clipboardData.getData('text/plain');
    if (!text) return;
    e.preventDefault();
    onPaste(parseTsv(text), active);
  };

  return { active, setActive, editing, draft, setDraft, error, startEdit, cancel, finish, toggle, onGridKeyDown, onGridPaste };
}
