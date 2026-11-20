/**
 * ResourceList / ResourceRow (DESIGN.md §6.10.4): the collection's ledger.
 * One bordered panel, a quiet column header, then rows of
 * [type glyph + title (+ reason line) | origin | status | time | overflow].
 * Inline rows (ProgressRow, AttentionBanner) slot in above the rows as
 * children of the list. A row in the `adding` state drops in (§8).
 */
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

const GRID = 'grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 md:grid-cols-[minmax(0,2.2fr)_minmax(0,1.4fr)_9rem_7rem_2rem]';

export interface ResourceListProps {
  /** Column labels for md+ screens. Pass null to hide the header. */
  columns?: [string, string, string, string] | null;
  /** Accessible name for the list, e.g. "Documents". */
  label: string;
  children: ReactNode;
  className?: string;
}

export function ResourceList({ columns = ['Name', 'Origin', 'Status', 'Added'], label, children, className }: ResourceListProps) {
  return (
    <div className={cn('overflow-hidden rounded border border-line bg-panel', className)} data-testid="resource-list">
      {columns && (
        <div aria-hidden="true" className={cn(GRID, 'hidden border-b border-line px-4 py-2 text-meta text-steel-soft md:grid')}>
          {columns.map((c) => (
            <div key={c}>{c}</div>
          ))}
          <div />
        </div>
      )}
      <ul aria-label={label} className="divide-y divide-line">
        {children}
      </ul>
    </div>
  );
}

/** Short file-type mark (PDF, DOCX, URL…). Monochrome on purpose: type is metadata, not status. */
export function TypeGlyph({ label, className }: { label: string; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-flex h-6 w-9 shrink-0 items-center justify-center rounded-sm border border-line bg-paper-deep font-mono text-meta uppercase text-steel',
        className,
      )}
    >
      {label.slice(0, 4)}
    </span>
  );
}

export interface ResourceRowProps {
  title: ReactNode;
  /** Glyph label, e.g. "pdf". Or pass `glyph` for a custom node. */
  type?: string;
  glyph?: ReactNode;
  /** Where it came from: "Upload", "S3 · bucket/path/". Rendered subtle and truncated. */
  origin?: ReactNode;
  /** Status pill, usually a <Badge variant="pill-*">. */
  status?: ReactNode;
  /** Relative time, e.g. "2 days ago". */
  time?: ReactNode;
  /** One plain sentence under the title explaining a problem, with its fix action. */
  reason?: ReactNode;
  /** Row overflow, usually an <OverflowMenu size="icon-sm">. */
  actions?: ReactNode;
  /** Arriving row: drop-in motion and a muted title until it settles. */
  adding?: boolean;
  /** Opens the item (detail sheet). The title becomes a button. */
  onOpen?: () => void;
  className?: string;
}

export function ResourceRow({ title, type, glyph, origin, status, time, reason, actions, adding, onOpen, className }: ResourceRowProps) {
  return (
    <li
      data-state={adding ? 'adding' : undefined}
      aria-busy={adding || undefined}
      className={cn(GRID, 'px-4 py-2.5 transition-colors hover:bg-paper-deep', adding && 'motion-safe:animate-drop', className)}
    >
      <div className="flex min-w-0 items-center gap-3">
        {glyph ?? (type ? <TypeGlyph label={type} /> : null)}
        <div className="min-w-0">
          {onOpen ? (
            <button
              type="button"
              onClick={onOpen}
              className={cn(
                'block max-w-full truncate rounded-sm text-left text-ui-text text-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                adding && 'text-steel',
              )}
            >
              {title}
            </button>
          ) : (
            <span className={cn('block truncate text-ui-text text-ink', adding && 'text-steel')}>{title}</span>
          )}
          {reason && <div className="mt-0.5 text-micro text-steel">{reason}</div>}
          {origin && <div className="truncate text-meta text-steel-soft md:hidden">{origin}</div>}
        </div>
      </div>
      <div className="hidden min-w-0 truncate font-mono text-meta text-steel-soft md:block">{origin}</div>
      <div className="flex items-center justify-end gap-2 md:justify-start">
        {status}
        <span className="md:hidden">{actions}</span>
      </div>
      <div className="hidden text-micro text-steel md:block">{time}</div>
      <div className="hidden justify-end md:flex">{actions}</div>
    </li>
  );
}

/** Full-width slot inside a ResourceList for a ProgressRow or AttentionBanner. */
export function ResourceListSlot({ children }: { children: ReactNode }) {
  return <li className="list-none">{children}</li>;
}
