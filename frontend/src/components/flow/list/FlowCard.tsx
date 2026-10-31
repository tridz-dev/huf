import { useMemo } from 'react';
import { CircleDashed, Copy, MoreHorizontal, Play, Settings, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { StatusPill } from '@/components/common/StatusPill';
import { NODE_ICONS } from '@/components/nodes/nodeIcons';
import { triggerOptions } from '@/data/triggers';
import { formatTimeAgo } from '@/utils/time';
import { cn } from '@/lib/utils';
import { RUN_BUTTON_LABEL } from '@/lib/flow-run/flowRunPayload';
import {
  cardDescription, cardStatusKind, descriptionIsGenerated, lastRunLine, runStatusKind, stepsText, triggerLine, visibleCategory,
} from '@/lib/flow-list/flowListSummary';
import type { FlowCard as FlowCardData } from '@/services/flow/flowCardsApi';
import { FlowStepStrip } from './FlowStepStrip';

/** What the play button is called: the Run dialog opens with Test run chosen. */
export const FLOW_CARD_RUN_LABEL = RUN_BUTTON_LABEL;

interface FlowCardProps {
  card: FlowCardData;
  /** May run, copy, change settings and delete (the same people the server lets write flows). */
  canManage: boolean;
  /** May create flows (needed for Duplicate). */
  canCreate: boolean;
  onOpen: () => void;
  onRun: () => void;
  onSettings: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}

const TRIGGER_ICON: Record<string, string | undefined> = Object.fromEntries(triggerOptions.map((t) => [t.id, t.icon]));

/**
 * One flow in the list: a clean title (two lines at most, full name on hover), what it does in plain words, what
 * starts it, how the last run went, and labelled actions. The whole card opens the flow.
 */
export function FlowCard({ card, canManage, canCreate, onOpen, onRun, onSettings, onDuplicate, onDelete }: FlowCardProps) {
  const statusKind = cardStatusKind(card);
  const TriggerIcon = (card.trigger.type !== 'unset' && NODE_ICONS[TRIGGER_ICON[card.trigger.type] ?? '']) || CircleDashed;
  const description = useMemo(() => cardDescription(card), [card]);
  const generated = descriptionIsGenerated(card);
  const category = visibleCategory(card.category);
  const runKind = card.last_run ? runStatusKind(card.last_run) : null;
  const lastRun = lastRunLine(card.last_run, (iso) => formatTimeAgo(iso));
  const runFailed = runKind === 'failed' || runKind === 'stuck';
  const id = card.flow_id;

  return (
    <Card
      className="group relative flex h-full cursor-pointer flex-col gap-3 p-4 transition-colors hover:border-ink"
      onClick={onOpen}
      data-testid={`flow-list-item-${id}`}
    >
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-line bg-background text-steel"
          title={triggerLine(card.trigger)}
          data-testid="flow-card-trigger-icon"
          data-trigger={card.trigger.type}
        >
          <TriggerIcon className="h-4 w-4" aria-hidden />
        </span>
        <h3
          className="min-w-0 flex-1 line-clamp-2 break-words text-body-text font-semibold leading-snug text-ink"
          title={card.flow_name}
          data-testid="flow-card-title"
        >
          {card.flow_name}
        </h3>
        <StatusPill kind={statusKind} data-testid={`flow-list-status-${id}`} />
      </div>

      <p
        className="line-clamp-2 min-h-[2.5rem] text-ui-text text-steel"
        title={card.description || undefined}
        data-testid="flow-card-description"
      >
        {description}
      </p>

      {card.step_count > 0 && (
        <div className="flex min-h-control-sm items-center justify-between gap-2">
          <FlowStepStrip steps={card.steps} total={card.step_count} data-testid="flow-card-steps" />
          <span className="shrink-0 text-xs text-steel">{stepsText(card.step_count)}</span>
        </div>
      )}

      <div className="space-y-1 text-xs">
        {!generated && (
          <p className="truncate text-steel" data-testid="flow-card-trigger">
            {triggerLine(card.trigger)}
          </p>
        )}
        <p
          className={cn('truncate', runFailed ? 'font-medium text-destructive' : 'text-steel')}
          title={card.last_run?.failed_step ? `Stopped at: ${card.last_run.failed_step}` : undefined}
          data-testid="flow-card-last-run"
          data-run-status={runKind ?? 'none'}
        >
          {lastRun}
          {card.last_run?.failed_step && runKind === 'failed' ? ` at "${card.last_run.failed_step}"` : ''}
        </p>
        {category && (
          <p className="truncate text-steel-soft" data-testid="flow-card-category">
            {category}
          </p>
        )}
      </div>

      <div className="mt-auto flex items-center gap-2 pt-1" onClick={(e) => e.stopPropagation()}>
        <Button size="sm" variant="outline" onClick={onOpen} data-testid="flow-card-open">
          Open
        </Button>
        {canManage && (
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            onClick={onRun}
            title="Run a test of this flow: nothing is sent unless you choose Run for real"
            data-testid="flow-card-run"
          >
            <Play className="h-3.5 w-3.5" aria-hidden />
            {FLOW_CARD_RUN_LABEL}
          </Button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              className="ml-auto"
              aria-label={`More actions for ${card.flow_name}`}
              title="More actions"
              data-testid="flow-card-menu"
            >
              <MoreHorizontal className="h-4 w-4" aria-hidden />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" data-testid="flow-card-menu-content">
            {canManage && canCreate && (
              <DropdownMenuItem onClick={onDuplicate} data-testid="flow-card-duplicate">
                <Copy className="mr-2 h-4 w-4" aria-hidden />
                Duplicate
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={onSettings} data-testid="flow-card-settings">
              <Settings className="mr-2 h-4 w-4" aria-hidden />
              {canManage ? 'Settings' : 'View settings'}
            </DropdownMenuItem>
            {canManage && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={onDelete}
                  className="text-destructive focus:text-destructive"
                  data-testid="flow-card-delete"
                >
                  <Trash2 className="mr-2 h-4 w-4" aria-hidden />
                  Delete
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </Card>
  );
}
