/**
 * Data-grid vocabulary (DESIGN.md §6.11). Column types are user words
 * (Text, Number, Dropdown, Date, Link, Checkbox, Currency), never storage
 * types. Formatting and parsing for every type live here, once.
 */
import {
  AlignLeft, Calendar, CheckSquare, DollarSign, Hash, Link2, ListFilter, Type, type LucideIcon,
} from 'lucide-react';
import type { Tone } from '@/components/patterns';

export type ColumnType = 'text' | 'longtext' | 'number' | 'currency' | 'date' | 'select' | 'link' | 'checkbox';

export interface ColumnOption {
  value: string;
  label?: string;
  /** Meaning of the option; mapped to a pill colour once (TONE_PILL). */
  tone?: Tone;
}

export type CellValue = string | number | boolean | null | undefined;

export interface GridColumn<R = Record<string, CellValue>> {
  key: string;
  label: string;
  type: ColumnType;
  /** Quiet tag after the label, e.g. "title" or "key". */
  tag?: string;
  width?: 'sm' | 'md' | 'lg';
  options?: ColumnOption[];
  /** ISO 4217 code for `currency`, default USD. */
  currency?: string;
  required?: boolean;
  readOnly?: boolean;
  /** Return a one-line fix hint, or null when the value is fine. */
  validate?: (value: CellValue, row: R) => string | null;
  getValue?: (row: R) => CellValue;
  /** Set false to keep this header static when the grid is sortable. */
  sortable?: boolean;
}

export const TYPE_LABEL: Record<ColumnType, string> = {
  text: 'Text',
  longtext: 'Long text',
  number: 'Number',
  currency: 'Currency',
  date: 'Date',
  select: 'Dropdown',
  link: 'Link',
  checkbox: 'Checkbox',
};

/** One glyph per type, shown in headers, field lists and mappers. */
export const TYPE_ICON: Record<ColumnType, LucideIcon> = {
  text: Type,
  longtext: AlignLeft,
  number: Hash,
  currency: DollarSign,
  date: Calendar,
  select: ListFilter,
  link: Link2,
  checkbox: CheckSquare,
};

export const TONE_PILL: Record<Tone, 'pill-success' | 'pill-info' | 'pill-warning' | 'pill-danger' | 'pill-neutral'> = {
  ready: 'pill-success',
  live: 'pill-info',
  attention: 'pill-warning',
  error: 'pill-danger',
  off: 'pill-neutral',
  neutral: 'pill-neutral',
};

export const WIDTH_CLASS: Record<NonNullable<GridColumn['width']>, string> = {
  sm: 'w-24 min-w-24',
  md: 'w-40 min-w-40',
  lg: 'w-64 min-w-64',
};

export const isNumeric = (t: ColumnType) => t === 'number' || t === 'currency';

/** Display string for a value (checkbox and select render richer elements). */
export function formatCell(col: Pick<GridColumn, 'type' | 'currency' | 'options'>, value: CellValue, locale?: string): string {
  if (value === null || value === undefined || value === '') return '';
  switch (col.type) {
    case 'number':
      return typeof value === 'number' ? value.toLocaleString(locale) : String(value);
    case 'currency':
      return typeof value === 'number'
        ? new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
        : String(value);
    case 'date': {
      const d = new Date(String(value));
      return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' });
    }
    case 'select':
      return col.options?.find((o) => o.value === value)?.label ?? String(value);
    case 'checkbox':
      return value ? 'Yes' : 'No';
    default:
      return String(value);
  }
}

/** Editor text back to a typed value. Returns `{ error }` for unparseable input. */
export function parseCell(type: ColumnType, text: string): { value: CellValue } | { error: string } {
  const t = text.trim();
  if (t === '') return { value: null };
  if (isNumeric(type)) {
    const n = Number(t.replace(/,/g, ''));
    return Number.isFinite(n) ? { value: n } : { error: 'Enter a number, like 1200 or 1,200.50' };
  }
  if (type === 'date') {
    return Number.isNaN(new Date(t).getTime()) ? { error: 'Enter a date, like 2026-12-10' } : { value: t };
  }
  return { value: text };
}

export const cellValue = <R,>(col: GridColumn<R>, row: R): CellValue =>
  col.getValue ? col.getValue(row) : (row as Record<string, CellValue>)[col.key];

/** Clipboard text (tab-separated, from a spreadsheet) to a matrix of cells. */
export function parseTsv(text: string): string[][] {
  // RFC 4180 style, with tab as the delimiter: a cell that starts with a quote
  // may hold tabs and newlines, and "" inside it is a literal quote.
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let i = 0;
  const n = text.length;
  while (i < n) {
    if (cell === '' && text[i] === '"') {
      i++;
      let quoted = '';
      let closed = false;
      while (i < n) {
        if (text[i] === '"') {
          if (text[i + 1] === '"') { quoted += '"'; i += 2; continue; }
          i++; closed = true; break;
        }
        quoted += text[i++];
      }
      // An unclosed quote, or text after the closing quote, is kept literally.
      cell = closed ? quoted : `"${quoted}`;
      while (i < n && text[i] !== '\t' && text[i] !== '\n' && text[i] !== '\r') cell += text[i++];
      continue;
    }
    const ch = text[i];
    if (ch === '\t') { row.push(cell); cell = ''; i++; continue; }
    if (ch === '\r' || ch === '\n') {
      row.push(cell); rows.push(row); row = []; cell = '';
      i += ch === '\r' && text[i + 1] === '\n' ? 2 : 1;
      continue;
    }
    cell += ch; i++;
  }
  if (cell !== '' || row.length > 0 || rows.length === 0) { row.push(cell); rows.push(row); }
  return rows;
}

/** One plain sentence per type, shown by ColumnTypePicker. */
export const TYPE_DESCRIPTION: Record<ColumnType, string> = {
  text: 'A short line, like a name or an email.',
  longtext: 'Paragraphs, like notes or a description.',
  number: 'Whole or decimal numbers you can add up.',
  currency: 'Money, shown with two decimals.',
  date: 'A calendar day, sortable oldest to newest.',
  select: 'One choice from a list you define.',
  link: 'Points to a record in another table.',
  checkbox: 'Yes or no.',
};

/* ---------- Sorting (§6.11.5) ---------- */

export type SortDirection = 'asc' | 'desc';
export interface GridSort {
  key: string;
  direction: SortDirection;
}

/** Header click cycle on one column: none → asc → desc → none. Another column starts at asc. */
export function nextSort(current: GridSort | null | undefined, key: string): GridSort | null {
  if (!current || current.key !== key) return { key, direction: 'asc' };
  return current.direction === 'asc' ? { key, direction: 'desc' } : null;
}

/** Type-aware direction words, shared by DataGrid headers and SortChip. */
export function sortDirectionLabel(type: ColumnType, direction: SortDirection): string {
  if (isNumeric(type)) return direction === 'asc' ? '1→9' : '9→1';
  if (type === 'date') return direction === 'asc' ? 'Oldest first' : 'Newest first';
  if (type === 'checkbox') return direction === 'asc' ? 'No first' : 'Yes first';
  return direction === 'asc' ? 'A→Z' : 'Z→A';
}
