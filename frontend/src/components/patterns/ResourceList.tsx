/**
 * ResourceList / ResourceRow (DESIGN.md §6.10.4): the collection's ledger.
 * One bordered panel, a quiet column header, then rows of
 * [type glyph + title (+ reason line) | origin | status | time | overflow].
 * Inline rows (ProgressRow, AttentionBanner) slot in above the rows as
 * children of the list. A row in the `adding` state drops in (§8).
 */
import { createContext, useContext, type CSSProperties, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

const GRID = 'grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 md:grid-cols-[minmax(0,2.2fr)_minmax(0,1.4fr)_9rem_7rem_2rem]';
/** Custom layouts read their md+ template from --rl-cols, set once on the list. */
const CUSTOM_GRID = 'grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 md:grid-cols-[var(--rl-cols)]';

/**
 * A configurable ResourceList column. The first column is always the title
 * cell (glyph + title + reason); the rest render `cells[key]` from each row.
 */
export interface ResourceColumn {
  key: string;
  label: string;
  /** CSS grid track, e.g. "8rem" or "minmax(0,2fr)". Default minmax(0,1fr). */
  width?: string;
  align?: 'start' | 'center' | 'end';
}

const ALIGN = { start: 'justify-start text-left', center: 'justify-center text-center', end: 'justify-end text-right' } as const;
const ColumnsCtx = createContext<ResourceColumn[] | null>(null);

export const resourceGridTemplate = (cols: ResourceColumn[]) => [...cols.map((c) => c.width ?? 'minmax(0,1fr)'), '2rem'].join(' ');

export interface ResourceListProps {
  /**
   * Column labels for md+ screens. Four labels keep the default ledger
   * (Name · Origin · Status · Added). Column defs switch to a custom layout
   * where rows pass `cells`. Pass null to hide the header.
   */
  columns?: [string, string, string, string] | ResourceColumn[] | null;
  /** Accessible name for the list, e.g. "Documents". */
  label: string;
  children: ReactNode;
  className?: string;
}

export function ResourceList({ columns = ['Name', 'Origin', 'Status', 'Added'], label, children, className }: ResourceListProps) {
  const defs = columns && typeof columns[0] === 'object' ? (columns as ResourceColumn[]) : null;
  const style = defs ? ({ '--rl-cols': resourceGridTemplate(defs) } as CSSProperties) : undefined;
  return (
    <div className={cn('overflow-hidden rounded border border-line bg-panel', className)} data-testid="resource-list" style={style}>
      {columns && (
        <div aria-hidden="true" className={cn(defs ? CUSTOM_GRID : GRID, 'hidden border-b border-line px-4 py-2 text-meta text-steel-soft md:grid')}>
          {defs
            ? defs.map((c) => <div key={c.key} className={cn('flex', ALIGN[c.align ?? 'start'])}>{c.label}</div>)
            : (columns as string[]).map((c) => <div key={c}>{c}</div>)}
          <div />
        </div>
      )}
      <ColumnsCtx.Provider value={defs}>
        <ul aria-label={label} className="divide-y divide-line">
          {children}
        </ul>
      </ColumnsCtx.Provider>
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
  /** Custom layout only: content per column key (columns after the first). */
  cells?: Record<string, ReactNode>;
  className?: string;
}

export function ResourceRow({ title, type, glyph, origin, status, time, reason, actions, adding, onOpen, cells, className }: ResourceRowProps) {
  const defs = useContext(ColumnsCtx);
  const titleCell = (
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
  );
  const rowProps = {
    'data-state': adding ? 'adding' : undefined,
    'aria-busy': adding || undefined,
  };
  const rowClass = (grid: string) => cn(grid, 'px-4 py-2.5 transition-colors hover:bg-paper-deep', adding && 'motion-safe:animate-drop', className);
  if (defs) {
    return (
      <li {...rowProps} className={rowClass(CUSTOM_GRID)}>
        {titleCell}
        {defs.slice(1).map((c) => (
          <div key={c.key} data-col={c.key} className={cn('hidden min-w-0 items-center text-micro text-steel md:flex', ALIGN[c.align ?? 'start'])}>
            {cells?.[c.key]}
          </div>
        ))}
        <div className="flex justify-end">{actions}</div>
      </li>
    );
  }
  return (
    <li {...rowProps} className={rowClass(GRID)}>
      {titleCell}
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
