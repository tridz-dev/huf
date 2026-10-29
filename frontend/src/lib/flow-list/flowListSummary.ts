import { actionOptions } from '@/data/actions';
import { describeCron } from '@/lib/flow-trigger/scheduleText';
import { actionCardId } from '@/lib/flow/flowLabels';
import type { StatusKind } from '@/components/common/StatusPill';
import type { FlowCard, FlowCardLastRun, FlowCardStep, FlowCardTrigger } from '@/services/flow/flowCardsApi';

/**
 * Plain words for the Flows list: what starts a flow, what it does in a line, and how the last run went.
 * Pure functions so every card reads the same way and the wording is unit tested.
 */

const DOC_EVENT_WORD: Record<string, string> = {
  after_insert: 'created',
  on_update: 'changed',
  on_submit: 'submitted',
  on_cancel: 'cancelled',
  on_trash: 'deleted',
};

/** "a web request arrives", "every day at 09:00", "a ToDo is created": finishes the sentence "Starts when ...". */
export function triggerPhrase(trigger: FlowCardTrigger | undefined): { text: string; scheduled: boolean } | null {
  switch (trigger?.type) {
    case 'webhook':
      return { text: 'a web request arrives', scheduled: false };
    case 'schedule': {
      const when = describeCron(trigger.cron).replace(/ \(server time\)$/, '');
      if (when.startsWith('No valid')) return null;
      if (when.startsWith('Custom schedule')) return { text: 'on a custom schedule', scheduled: true };
      return { text: when.charAt(0).toLowerCase() + when.slice(1), scheduled: true };
    }
    case 'doc-event': {
      const event = trigger.event ? DOC_EVENT_WORD[trigger.event] : undefined;
      const doctype = trigger.doctype?.trim();
      if (!doctype) return { text: 'a record changes', scheduled: false };
      return { text: `a ${doctype} is ${event ?? 'changed'}`, scheduled: false };
    }
    default:
      return null;
  }
}

/** "Starts when a request arrives", "Starts every day at 09:00", or "Choose what starts this flow". */
export function triggerLine(trigger: FlowCardTrigger | undefined): string {
  const phrase = triggerPhrase(trigger);
  if (!phrase) return 'Choose what starts this flow';
  return phrase.scheduled ? `Starts ${phrase.text}` : `Starts when ${phrase.text}`;
}

/** "no steps yet", "1 step", "3 steps". */
export function stepsText(count: number): string {
  return count === 0 ? 'no steps yet' : count === 1 ? '1 step' : `${count} steps`;
}

/** A one-line summary written for people: "Starts when a web request arrives, then 3 steps." */
export function generatedSummary(card: Pick<FlowCard, 'trigger' | 'step_count'>): string {
  const phrase = triggerPhrase(card.trigger);
  if (!phrase) return card.step_count > 0 ? `Has ${stepsText(card.step_count)}. Choose what starts it.` : 'Nothing set up yet. Open it to choose what starts it.';
  const lead = triggerLine(card.trigger);
  return card.step_count > 0 ? `${lead}, then ${stepsText(card.step_count)}.` : `${lead}.`;
}

/** Descriptions that are engine notation ("Webhook -> Transform -> End", pasted JSON) are not shown as they are. */
export function isEngineNotation(text: string): boolean {
  return /->|=>|→/.test(text) || /\{\s*["'][^}]*["']\s*:/.test(text);
}

/** True when the card shows a generated summary (the author wrote nothing, or wrote engine notation). */
export function descriptionIsGenerated(card: Pick<FlowCard, 'description'>): boolean {
  const own = (card.description || '').trim();
  return !own || isEngineNotation(own);
}

/** The line under the title: the author's own description when it reads like a sentence, otherwise a summary. */
export function cardDescription(card: Pick<FlowCard, 'description' | 'trigger' | 'step_count'>): string {
  return descriptionIsGenerated(card) ? generatedSummary(card) : card.description.trim();
}

/** Category worth showing on a card: nothing for "no category" or the placeholder "Uncategorized". */
export function visibleCategory(category: string | null | undefined): string {
  const c = (category || '').trim();
  return c.toLowerCase() === 'uncategorized' ? '' : c;
}

/** Palette id (data/actions.ts) of a step in the card strip: its icon and plain name come from there. */
export function stepPaletteId(step: FlowCardStep): string {
  switch (step.type) {
    case 'agent.run': return 'agent-run';
    case 'router.llm':
    case 'router.decision': return 'router';
    case 'foreach': return 'loop';
    case 'output': return 'end';
    case 'tool.call': {
      const id = actionCardId({ type: 'tool-call', tool_id: step.tool_id });
      return id === 'tool-call' ? 'tool-call' : id;
    }
    case 'state.get': return 'state-get';
    case 'state.set': return 'state-set';
    case 'state.delete': return 'state-delete';
    case 'doc.create': return 'doc-create';
    case 'code.run': return 'code-run';
    default: return step.type; // condition, human.approval, transform, validate
  }
}

/** Icon name and plain name for a step in the strip. */
export function stepInfo(step: FlowCardStep): { icon: string; name: string } {
  const option = actionOptions.find((o) => o.id === stepPaletteId(step));
  return { icon: option?.icon ?? 'CircleDashed', name: option?.name ?? 'Step' };
}

/** Run status kind shown on a card, from the stored run status. */
export function runStatusKind(run: Pick<FlowCardLastRun, 'status' | 'stale'>): StatusKind {
  if (run.stale) return 'stuck';
  switch (run.status) {
    case 'Success': return 'finished';
    case 'Failed': return 'failed';
    case 'Running': return 'running';
    case 'Queued': return 'queued';
    case 'Waiting Approval':
    case 'Waiting User': return 'waiting_approval';
    case 'Waiting Code': return 'waiting_review';
    default: return 'queued';
  }
}

const RUN_WORD: Record<string, string> = {
  Success: 'Finished',
  Failed: 'Failed',
  Running: 'Running',
  Queued: 'Queued',
  'Waiting Approval': 'Waiting for approval',
  'Waiting User': 'Waiting for you',
  'Waiting Code': 'Waiting for code review',
};

/** "Last run: Finished 2 mins ago", or "Not run yet". `ago` turns an ISO time into "2 mins ago". */
export function lastRunLine(run: FlowCardLastRun | null | undefined, ago: (iso: string | null) => string): string {
  if (!run) return 'Not run yet';
  const word = run.stale ? 'Stuck' : (RUN_WORD[run.status] ?? run.status);
  const when = run.at ? ago(run.at) : '';
  return when ? `Last run: ${word} ${when.charAt(0).toLowerCase()}${when.slice(1)}` : `Last run: ${word}`;
}

/** The card's status kind: a live flow whose last run failed "Has problems"; otherwise Draft / Live (Archived stays). */
export function cardStatusKind(card: Pick<FlowCard, 'status' | 'last_run'>): StatusKind {
  if (card.status === 'Archived') return 'archived';
  if (card.status === 'Active') return card.last_run?.status === 'Failed' ? 'has_problems' : 'live';
  return 'draft';
}

/** Words people can type into the search box that find this card: name, description, category and the trigger line. */
export function matchesSearch(card: FlowCard, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [card.flow_name, card.description, card.category].some((v) => (v || '').toLowerCase().includes(q));
}
