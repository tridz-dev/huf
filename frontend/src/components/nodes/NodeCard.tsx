import type { CSSProperties, ReactNode } from 'react';
import { AlertCircle, CheckCircle2, Clock, Loader2, MinusCircle, Plug, Trash2, Unlink, XCircle, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useStore } from 'reactflow';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { cn } from '@/lib/utils';
import { NODE_CARD_BASE, NODE_ICON_WELL } from './nodeStyles';
import { compactGrowth, counterScale, lodForKey, tileIconSize, zoomKey, zoomOfKey } from '@/lib/flow-canvas/zoomLod';
import type { CardStatus, CardStatusKind } from '../../lib/flow/flowNodeCard';

/**
 * The one card layout for every step on the canvas: icon, ONE title line (full text in the tooltip), ONE
 * subtitle line saying what the step does, ONE status line. Fixed size, so a card never grows when its state
 * changes. Text is never broken inside a word; long text is cut with an ellipsis and kept in the tooltip.
 *
 * Semantic zoom (UX_DESIGN_DECISIONS (f)): at 80% and up the card is shown in full; from 50% to 80% only icon, title
 * and a status dot (the content is enlarged so the title stays readable); under 50% an icon tile whose title appears
 * on hover. The card keeps one size in every case, so connections never move when the zoom changes.
 */

const STATUS_STYLE: Record<CardStatusKind, { text: string; icon: LucideIcon | null; spin?: boolean }> = {
  ready: { text: 'text-steel', icon: null },
  'needs-setup': { text: 'text-warning', icon: AlertCircle },
  'not-connected': { text: 'text-warning', icon: Plug },
  orphan: { text: 'text-warning', icon: Unlink },
  running: { text: 'text-signal-ink', icon: Loader2, spin: true },
  waiting: { text: 'text-warning', icon: Clock },
  done: { text: 'text-good', icon: CheckCircle2 },
  failed: { text: 'text-destructive', icon: XCircle },
  skipped: { text: 'text-steel', icon: MinusCircle },
};

/** Colour of the status dot shown when the card is too small for the status word. */
const DOT_STYLE: Record<CardStatusKind, string> = {
  ready: 'bg-good',
  'needs-setup': 'bg-warning',
  'not-connected': 'bg-warning',
  orphan: 'bg-warning',
  running: 'bg-signal motion-safe:animate-pulse',
  waiting: 'bg-warning',
  done: 'bg-good',
  failed: 'bg-destructive',
  skipped: 'bg-steel-soft',
};

/** Test ids that existed before the status line was unified (docs/flow/TESTIDS.md); kept so they stay stable. */
const LEGACY_STATUS_TESTID: Partial<Record<CardStatusKind, (id: string) => string>> = {
  'needs-setup': (id) => `flow-node-incomplete-${id}`,
  orphan: (id) => `flow-node-orphan-${id}`,
};

export function CardStatusLine({
  id,
  status,
  title,
  action,
  marker,
}: {
  id: string;
  status: CardStatus;
  title?: string;
  /** Inline action next to the word (for example "Connect"). */
  action?: ReactNode;
  /** Small label pinned to the right: "Trigger" or "End". */
  marker?: { text: string; testId: string };
}) {
  const style = STATUS_STYLE[status.kind];
  const Icon = style.icon;
  return (
    <div className="flex min-w-0 items-center gap-2 text-xs leading-tight">
      <span
        className={cn('flex min-w-0 items-center gap-1 whitespace-nowrap font-medium', style.text)}
        data-testid={`flow-node-status-${id}`}
        data-status={status.kind}
        title={title}
      >
        {Icon ? (
          <Icon className={cn('h-3.5 w-3.5 shrink-0', style.spin && 'motion-safe:animate-spin')} aria-hidden />
        ) : (
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-good" aria-hidden />
        )}
        <span className="truncate" data-testid={LEGACY_STATUS_TESTID[status.kind]?.(id)}>{status.text}</span>
      </span>
      {action}
      {marker && (
        <span
          className="ml-auto shrink-0 rounded border border-line bg-paper-deep px-1.5 py-px text-eyebrow font-medium uppercase text-steel"
          data-testid={marker.testId}
        >
          {marker.text}
        </span>
      )}
    </div>
  );
}

export function ConnectLink({ to, label, testId, ariaLabel }: { to: string; label: string; testId: string; ariaLabel: string }) {
  return (
    <Link
      to={to}
      className="shrink-0 text-xs font-medium text-primary underline underline-offset-2"
      data-testid={testId}
      aria-label={ariaLabel}
      onClick={(e) => e.stopPropagation()}
    >
      {label}
    </Link>
  );
}

interface NodeCardProps {
  id: string;
  icon: LucideIcon;
  /** Tint of the icon well, for example `text-good`. */
  iconClass?: string;
  title: string;
  subtitle?: string;
  /** Border / ring classes from `getExecutionStatusClasses`. */
  frameClass: string;
  /** The status line (or a call to action in its place). */
  footer: ReactNode;
  /** The status the card is in: the dot of a small card. */
  status: CardStatus;
  /** One plain line about what this step produced in the run shown on the canvas; appears on hover. */
  runSummary?: string;
  /** Delete button, shown on the selected card. */
  onDelete?: (e: React.MouseEvent) => void;
  deleteLabel?: string;
  deleteId?: string;
  /** Let the title use two lines (only the empty trigger card does). */
  titleWraps?: boolean;
}

/** Sizes that depend on the zoom (card content grows as the canvas shrinks): the one place geometry is set inline. */
const sized = (style: CSSProperties): CSSProperties => style;
const square = (px: number): CSSProperties => ({ width: px, height: px });

/** Hover note under a card: the step's title when the card is only an icon, and what it produced in the shown run. */
function HoverNote({ id, zoom, title, summary }: { id: string; zoom: number; title?: string; summary?: string }) {
  if (!title && !summary) return null;
  const style: CSSProperties = { transform: `translateX(-50%) scale(${counterScale(zoom)})`, transformOrigin: 'top center' };
  return (
    <div
      className="pointer-events-none absolute left-1/2 top-full z-30 mt-1.5 hidden w-max max-w-[260px] rounded-md border border-line bg-panel px-2 py-1 text-left text-xs leading-snug text-ink shadow-md group-hover/card:block [.react-flow__node.selected_&]:block [.react-flow__node:focus-visible_&]:block"
      style={style}
      data-testid={`flow-node-hover-${id}`}
    >
      {title && <div className="truncate font-medium" data-testid={`flow-node-title-${id}`}>{title}</div>}
      {summary && <div className="line-clamp-3 break-words text-steel" data-testid={`flow-node-run-summary-${id}`}>{summary}</div>}
    </div>
  );
}

export function NodeCard({ id, icon: Icon, iconClass, title, subtitle, frameClass, footer, status, runSummary, onDelete, deleteLabel, deleteId, titleWraps }: NodeCardProps) {
  const key = useStore((s) => zoomKey(s.transform[2]));
  const lod = lodForKey(key);
  const zoom = zoomOfKey(key);
  const deleteButton = onDelete && (
    <Button
      variant="outline"
      size="icon-sm"
      className="absolute -right-2 -top-2 z-10 rounded-full bg-panel text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
      style={lod === 'full' ? undefined : { transform: `scale(${Math.min(counterScale(zoom), 2.2)})`, transformOrigin: 'top right' }}
      onClick={onDelete}
      data-testid={deleteId ?? `flow-node-delete-${id}`}
      aria-label={deleteLabel}
      title={deleteLabel}
    >
      <Trash2 className="h-3.5 w-3.5" />
    </Button>
  );
  const dot = (size: number) => (
    <span
      className={cn('inline-block shrink-0 rounded-full', DOT_STYLE[status.kind])}
      style={square(size)}
      data-testid={`flow-node-status-${id}`}
      data-status={status.kind}
      role="img"
      aria-label={status.text}
      title={status.text}
    />
  );

  if (lod === 'icon') {
    const size = tileIconSize(zoom);
    return (
      <div className="relative flex h-[100px] w-[236px] items-center justify-center" data-lod="icon">
        <div className={cn('flow-card group/card relative flex h-[100px] w-[120px] items-center justify-center rounded-2xl border bg-paper-deep shadow-sm transition-colors duration-200', frameClass)}>
          <div className={cn('text-ink', iconClass)}>
            <Icon style={square(size)} aria-hidden />
          </div>
          <span className="absolute right-2 top-2">{dot(Math.round(Math.min(10 * counterScale(zoom), 28)))}</span>
          <HoverNote id={id} zoom={zoom} title={title} summary={runSummary} />
        </div>
        {deleteButton}
      </div>
    );
  }

  if (lod === 'compact') {
    const k = compactGrowth(zoom);
    return (
      <Card className={cn(NODE_CARD_BASE, 'flow-card group/card !justify-center', frameClass)} data-lod="compact">
        {deleteButton}
        <div className="flex min-w-0 items-center" style={sized({ gap: 10 * k })}>
          <div className={cn(NODE_ICON_WELL, 'shrink-0 text-ink', iconClass)} style={sized({ width: 28 * k, height: 28 * k, borderRadius: 8 * k })}>
            <Icon style={square(20 * k)} aria-hidden />
          </div>
          <div
            className="min-w-0 flex-1 line-clamp-2 break-words font-medium leading-tight text-card-foreground"
            style={sized({ fontSize: 14 * k })}
            title={title}
            data-testid={`flow-node-title-${id}`}
          >
            {title}
          </div>
          {dot(Math.round(9 * k))}
        </div>
        <HoverNote id={id} zoom={zoom} summary={runSummary} />
      </Card>
    );
  }

  return (
    <Card className={cn(NODE_CARD_BASE, 'flow-card group/card', frameClass)} data-lod="full">
      {deleteButton}
      <div className="flex min-w-0 items-start gap-2.5">
        <div className={cn(NODE_ICON_WELL, 'shrink-0 text-ink', iconClass)}>
          <Icon className="h-5 w-5" aria-hidden />
        </div>
        <div className="min-w-0 flex-1 space-y-0.5">
          <div
            className={cn('text-sm font-medium leading-snug text-card-foreground', titleWraps ? 'line-clamp-2 text-balance' : 'truncate')}
            title={title}
            data-testid={`flow-node-title-${id}`}
          >
            {title}
          </div>
          {subtitle && (
            <div className="truncate text-xs leading-snug text-muted-foreground" title={subtitle} data-testid={`flow-node-subtitle-${id}`}>
              {subtitle}
            </div>
          )}
          {footer}
        </div>
      </div>
      <HoverNote id={id} zoom={zoom} summary={runSummary} />
    </Card>
  );
}
