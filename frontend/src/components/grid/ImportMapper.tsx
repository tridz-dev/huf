/**
 * ImportMapper (DESIGN.md §6.11.11): the review step of any file import.
 * One row per incoming column: source header + sample values → target field
 * (or "Don't import"), detected type, and a per-column check in plain words.
 * Below: a preview of the first rows and the rejected rows with reasons, so
 * people import the valid rows and download the rest to fix.
 */
import type { ReactNode } from 'react';
import { ArrowRight, CheckCircle2, Download, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { TYPE_ICON, TYPE_LABEL, type ColumnType } from './types';

export const SKIP_COLUMN = '__skip__';

export interface SourceColumn {
  header: string;
  samples: string[];
  detected?: ColumnType;
  /** Mapped target key, or null for "Don't import". */
  target: string | null;
  /** Rows in this column that won't fit the target, with a plain reason. */
  problems?: { count: number; reason: string };
}

export interface TargetField {
  key: string;
  label: string;
  type: ColumnType;
}

export interface RejectedRow {
  row: number;
  reason: string;
}

export interface ImportMapperProps {
  columns: SourceColumn[];
  targets: TargetField[];
  onMap: (header: string, target: string | null) => void;
  /** Offer "New field" in the target list. */
  onCreateTarget?: (header: string) => void;
  preview?: { headers: string[]; rows: string[][] };
  rejected?: RejectedRow[];
  totals: { valid: number; rejected: number };
  onDownloadRejected?: () => void;
  /** Mode picker etc. rendered above the mapping. */
  header?: ReactNode;
  className?: string;
}

const NEW = '__new__';

export function ImportMapper({ columns, targets, onMap, onCreateTarget, preview, rejected = [], totals, onDownloadRejected, header, className }: ImportMapperProps) {
  return (
    <div className={cn('space-y-5', className)}>
      {header}
      <table aria-label="Column mapping" className="w-full border-separate border-spacing-0 text-ui-text">
        <thead>
          <tr className="text-left text-micro text-steel">
            <th className="pb-2 font-medium">In your file</th>
            <th aria-hidden="true" className="w-8" />
            <th className="pb-2 font-medium">Goes to</th>
            <th className="pb-2 font-medium">Check</th>
          </tr>
        </thead>
        <tbody>
          {columns.map((col) => {
            const t = targets.find((x) => x.key === col.target);
            const Icon = t ? TYPE_ICON[t.type] : col.detected ? TYPE_ICON[col.detected] : null;
            return (
              <tr key={col.header} className="align-top">
                <td className="border-t border-line py-2.5 pr-3">
                  <span className="font-medium text-ink">{col.header}</span>
                  <span className="block truncate font-mono text-meta text-steel-soft">{col.samples.slice(0, 3).join(' · ')}</span>
                </td>
                <td aria-hidden="true" className="border-t border-line py-3 text-steel-soft"><ArrowRight className="h-3.5 w-3.5" /></td>
                <td className="w-56 border-t border-line py-2">
                  <Select value={col.target ?? SKIP_COLUMN}
                    onValueChange={(v) => (v === NEW ? onCreateTarget?.(col.header) : onMap(col.header, v === SKIP_COLUMN ? null : v))}>
                    <SelectTrigger size="sm" aria-label={`Field for ${col.header}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {targets.map((f) => (
                        <SelectItem key={f.key} value={f.key}>{f.label} <span className="text-steel">· {TYPE_LABEL[f.type]}</span></SelectItem>
                      ))}
                      <SelectSeparator />
                      {onCreateTarget && <SelectItem value={NEW}>New field “{col.header}”</SelectItem>}
                      <SelectItem value={SKIP_COLUMN}>Don’t import</SelectItem>
                    </SelectContent>
                  </Select>
                </td>
                <td className="border-t border-line py-2.5 pl-3 text-micro">
                  {col.target === null ? (
                    <span className="text-steel">Skipped</span>
                  ) : col.problems && col.problems.count > 0 ? (
                    <span className="inline-flex items-center gap-1.5 text-warning">
                      <AlertTriangle aria-hidden="true" className="h-3.5 w-3.5" />
                      {col.problems.count.toLocaleString()} {col.problems.reason}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-good">
                      {Icon ? <Icon aria-hidden="true" className="h-3.5 w-3.5" /> : <CheckCircle2 aria-hidden="true" className="h-3.5 w-3.5" />}
                      All valid
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {preview && preview.rows.length > 0 && (
        <section aria-label="Preview" className="space-y-2">
          <h3 className="text-micro font-semibold text-steel">Preview · first {preview.rows.length} rows</h3>
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-micro">
              <thead className="bg-paper-deep text-left text-steel">
                <tr>{preview.headers.map((h) => <th key={h} className="px-3 py-1.5 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody>
                {preview.rows.map((r, i) => (
                  <tr key={i} className="border-t border-line">{r.map((c, j) => <td key={j} className="truncate px-3 py-1.5">{c}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section aria-label="Result" className="flex flex-wrap items-center gap-3 rounded-lg bg-paper-deep px-4 py-3 text-ui-text">
        <span role="status"><span className="font-mono">{totals.valid.toLocaleString()}</span> rows ready to import</span>
        {totals.rejected > 0 && (
          <span className="text-warning"><span className="font-mono">{totals.rejected.toLocaleString()}</span> rows can’t be imported</span>
        )}
        {totals.rejected > 0 && onDownloadRejected && (
          <Button size="sm" variant="outline" className="ml-auto gap-1.5" onClick={onDownloadRejected}>
            <Download aria-hidden="true" className="h-3.5 w-3.5" /> Download rejected rows
          </Button>
        )}
      </section>
      {rejected.length > 0 && (
        <ul aria-label="Rejected rows" className="max-h-40 space-y-1 overflow-y-auto text-micro">
          {rejected.map((r) => (
            <li key={r.row} className="flex gap-3"><span className="w-16 shrink-0 font-mono text-steel">Row {r.row}</span><span>{r.reason}</span></li>
          ))}
        </ul>
      )}
    </div>
  );
}
