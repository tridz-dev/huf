import type { ReactNode } from 'react';
import { AlertCircle, CheckCircle2, Clock, Loader2, Plug, Trash2, Unlink, XCircle, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { cn } from '@/lib/utils';
import { NODE_CARD_BASE, NODE_ICON_WELL } from './nodeStyles';
import type { CardStatus, CardStatusKind } from '../../lib/flow/flowNodeCard';

/**
 * The one card layout for every step on the canvas: icon, ONE title line (full text in the tooltip), ONE
 * subtitle line saying what the step does, ONE status line. Fixed size, so a card never grows when its state
 * changes. Text is never broken inside a word; long text is cut with an ellipsis and kept in the tooltip.
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
          <Icon className={cn('h-3.5 w-3.5 shrink-0', style.spin && 'animate-spin')} aria-hidden />
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
  /** Delete button, shown on the selected card. */
  onDelete?: (e: React.MouseEvent) => void;
  deleteLabel?: string;
  deleteId?: string;
  /** Let the title use two lines (only the empty trigger card does). */
  titleWraps?: boolean;
}

export function NodeCard({ id, icon: Icon, iconClass, title, subtitle, frameClass, footer, onDelete, deleteLabel, deleteId, titleWraps }: NodeCardProps) {
  return (
    <Card className={cn(NODE_CARD_BASE, frameClass)}>
      {onDelete && (
        <Button
          variant="outline"
          size="icon-sm"
          className="absolute -right-2 -top-2 rounded-full bg-panel text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          onClick={onDelete}
          data-testid={deleteId ?? `flow-node-delete-${id}`}
          aria-label={deleteLabel}
          title={deleteLabel}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      )}
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
    </Card>
  );
}
