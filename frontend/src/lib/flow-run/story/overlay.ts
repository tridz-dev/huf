import type { FlowRunDetail } from '@/services/flowApi';
import { humanizeSentence } from '../humanize';
import { redactSecrets } from '@/lib/flow/flowToolSummary';
import { buildRunStory, type StepStatus, type StoryStep } from './runSteps';

/** What a run did at one step, for the canvas: a status and a short plain summary. */
export interface NodeRunState {
  status: StepStatus;
  /** At most ~80 characters; empty when the step produced nothing worth showing. */
  summary: string;
}

const MAX_SUMMARY = 80;

function summaryOf(step: StoryStep): string {
  const text = step.status === 'failed' || step.status === 'stopped'
    ? step.reason ?? ''
    : step.sentence ?? (step.iterations ? `${step.iterations.count} ${step.iterations.count === 1 ? 'round' : 'rounds'}` : humanizeSentence(redactSecrets(step.output), {}, 2));
  const one = text.replace(/\s+/g, ' ').trim();
  return one.length > MAX_SUMMARY ? `${one.slice(0, MAX_SUMMARY - 1).trimEnd()}…` : one;
}

/** Per-step state of a run, keyed by step id (loop body steps included). Steps the run never reached are absent. */
export function overlayFromRun(run: FlowRunDetail, titleOf: (id: string) => string | null = (id) => run.node_labels?.[id] ?? id): Record<string, NodeRunState> {
  const out: Record<string, NodeRunState> = {};
  const visit = (step: StoryStep) => {
    out[step.id] = { status: step.status, summary: summaryOf(step) };
    step.children?.forEach(visit);
  };
  buildRunStory(run, { titleOf }).steps.forEach(visit);
  return out;
}
