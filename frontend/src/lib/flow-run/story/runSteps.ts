import type { FlowRunDetail } from '@/services/flowApi';
import { isFailedStepOutput, titleNodeIds, withoutFailureKeys } from '../flowRunFormat';
import { placeTriggerInput } from '../humanize';
import { summarizeDocPayload } from '../flowRunDoc';
import { friendlyClock } from './time';
import { plainRunError } from './runErrors';
import { stoppedByPerson } from './runStatus';
import { stepPhrase } from './stepWords';

export type StepStatus = 'done' | 'failed' | 'waiting' | 'stopped';

export interface StoryStep {
  id: string;
  type: string;
  /** The step's own name, as it is on the canvas. */
  title: string;
  /** What it did, in plain words ("Received a webhook"). */
  phrase: string;
  status: StepStatus;
  output: unknown;
  /** A one-line summary shown under the heading (decision, answer, chosen path...). */
  sentence?: string;
  comment?: string;
  footnote?: string;
  /** Labelled facts worth showing next to the sentence. */
  facts?: Array<{ label: string; value: string }>;
  /** The step's data is fully told by the sentence: the labelled rows are left out (still under "Raw"). */
  hideOutput?: boolean;
  /** Why it failed (plain), or why it was stopped. */
  reason?: string | null;
  /** Loop: how many times the body ran, what each round produced, and the body steps. */
  iterations?: { count: number; results: unknown[] };
  children?: StoryStep[];
  /** The data the run started with, shown inside the first step. */
  receivedData?: unknown;
}

export interface RunStory {
  steps: StoryStep[];
  /** Every step card shown, loop body steps included, each counted once. */
  stepCount: number;
  /** The run started with a document, shown in its own block instead of the first step. */
  documentInput: boolean;
  /** Data the run started with that no step repeats (shown in its own block). */
  separateInput: boolean;
  input: Record<string, unknown>;
}

const DECISION_WORDS: Record<string, string> = { approved: 'Approved', rejected: 'Rejected', timeout: 'Timed out' };
const INTERNAL_TOKENS = new Set(['approved', 'rejected', 'timeout', 'done', 'ok']);

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

function decisionSentence(output: unknown): { sentence: string; comment?: string } | null {
  if (!isObj(output) || typeof output.decision !== 'string' || !(output.decision in DECISION_WORDS)) return null;
  const word = DECISION_WORDS[output.decision];
  const comment = typeof output.comment === 'string' && output.comment.trim() ? output.comment.trim() : undefined;
  if (output.decision === 'timeout') return { sentence: 'Timed out with no answer', comment };
  const by = typeof output.decided_by === 'string' && output.decided_by ? ` by ${output.decided_by}` : '';
  const at = typeof output.decided_at === 'string' && friendlyClock(output.decided_at) ? `, ${friendlyClock(output.decided_at)}` : '';
  return { sentence: `${word}${by}${at}`, comment };
}

function waitingFor(waiting: Record<string, unknown> | undefined): string | undefined {
  if (!waiting || waiting.type !== 'approval') return undefined;
  const users = Array.isArray(waiting.approver_users) ? (waiting.approver_users as unknown[]).filter((u) => typeof u === 'string') : [];
  if (waiting.approver_type === 'role' && typeof waiting.approver_role === 'string' && waiting.approver_role) return `Waiting for someone with the ${waiting.approver_role} role`;
  if (users.length) return `Waiting for ${users.join(', ')}`;
  return undefined;
}

/** Step-specific plain words; everything else falls back to labelled rows in the card. */
function describe(type: string, output: unknown, title: (id: string) => string | null, outcomeLabel?: string): Partial<StoryStep> {
  if (type === 'human.approval') {
    const d = decisionSentence(output);
    return d ? { sentence: d.sentence, comment: d.comment, hideOutput: true } : {};
  }
  if (type === 'condition' && typeof output === 'boolean') return { sentence: output ? 'The answer was yes' : 'The answer was no', hideOutput: true };
  if ((type === 'router.llm' || type === 'router.decision') && isObj(output)) {
    const shown = titleNodeIds(output, title) as Record<string, unknown>;
    const choice = typeof shown.label === 'string' && shown.label ? shown.label : typeof shown.node_id === 'string' ? shown.node_id : '';
    if (!choice) return {};
    const facts = typeof shown.reason === 'string' && shown.reason && shown.reason !== 'matched' ? [{ label: 'Why', value: shown.reason }] : undefined;
    const model = typeof shown.model === 'string' && shown.model ? `Decided by ${shown.model}` : undefined;
    return { sentence: `Chose "${choice}"`, facts, footnote: model, hideOutput: true };
  }
  if (type === 'output') {
    const token = typeof output === 'string' && INTERNAL_TOKENS.has(output.trim().toLowerCase());
    return { sentence: outcomeLabel, hideOutput: token || output === null || output === undefined };
  }
  return {};
}

interface BuildOptions {
  titleOf: (id: string) => string | null;
}

/** The run as a list of steps in plain words: loop bodies grouped under their loop, trigger input merged into step 1. */
export function buildRunStory(run: FlowRunDetail, { titleOf }: BuildOptions): RunStory {
  const { __node_outputs__: rawOutputs, ...input } = run.context_json ?? {};
  const outputs = (isObj(rawOutputs) ? rawOutputs : {}) as Record<string, unknown>;
  const meta = run.step_meta ?? {};
  const byPerson = run.status === 'Failed' ? stoppedByPerson(run.last_error) : null;
  const waitingRun = !!run.status?.startsWith('Waiting');
  const current = run.current_node_id || undefined;
  const nameOf = (id: string) => titleOf(id) ?? id;
  const bodyOf = new Map<string, string>();
  Object.entries(meta).forEach(([id, m]) => (m.body ?? []).forEach((b) => bodyOf.set(b, id)));

  let ids = Object.keys(outputs);
  if (current && !ids.includes(current) && (run.status === 'Failed' || waitingRun)) ids.push(current);
  // A loop whose body ran but that has no result yet (still running or failed inside) comes before its body.
  const withLoops: string[] = [];
  ids.forEach((id) => {
    const loop = bodyOf.get(id);
    if (loop && !ids.includes(loop) && !withLoops.includes(loop)) withLoops.push(loop);
    withLoops.push(id);
  });
  ids = withLoops;

  const failedHere = (id: string, output: unknown) => (run.status === 'Failed' && id === current && !byPerson) || isFailedStepOutput(output);

  const make = (id: string): StoryStep => {
    const output = outputs[id];
    const type = meta[id]?.type ?? '';
    const title = nameOf(id);
    const failed = failedHere(id, output);
    const stopped = !!byPerson && run.status === 'Failed' && id === current;
    const waiting = waitingRun && id === current && (!(id in outputs) || type === 'code.run');
    const status: StepStatus = failed ? 'failed' : stopped ? 'stopped' : waiting ? 'waiting' : 'done';
    const own = isObj(output) && typeof output.error === 'string' && output.error ? output.error : null;
    const reasonRaw = own ?? (failed && run.last_error ? run.last_error : null);
    const step: StoryStep = {
      id,
      type,
      title,
      phrase: stepPhrase(type, status, title),
      status,
      output: failed ? withoutFailureKeys(output) : output,
      ...(status === 'done' ? describe(type, output, titleOf, run.outcome?.label !== title ? run.outcome?.label : undefined) : {}),
    };
    if (failed) step.hideOutput = true;
    if (failed && reasonRaw) step.reason = plainRunError(reasonRaw, title);
    if (stopped && byPerson) {
      step.reason = `Stopped by ${byPerson.by}. ${byPerson.why}`;
      step.output = undefined;
    }
    if (status === 'waiting') {
      step.sentence = waitingFor(run.waiting);
      step.output = undefined;
    }
    if (status === 'failed' && isObj(step.output) && Object.keys(step.output).length === 0) step.output = undefined;
    return step;
  };

  const steps: StoryStep[] = [];
  ids.forEach((id) => {
    if (bodyOf.has(id)) return;
    const step = make(id);
    const body = meta[id]?.body;
    if (step.type === 'foreach' && body) {
      step.children = body.filter((b) => ids.includes(b)).map(make);
      const results = isObj(outputs[id]) && Array.isArray((outputs[id] as { result?: unknown }).result) ? ((outputs[id] as { result: unknown[] }).result) : Array.isArray(outputs[id]) ? (outputs[id] as unknown[]) : [];
      if (step.status === 'done') step.iterations = { count: results.length, results };
      step.hideOutput = true;
      if (step.children.some((c) => c.status === 'failed') && step.status === 'done') step.status = 'failed';
    }
    steps.push(step);
  });

  const doc = summarizeDocPayload(input, run.trigger_event);
  const placement = doc ? ({ mode: 'none' } as const) : placeTriggerInput(input, steps.map((s) => ({ id: s.id, output: s.output })));
  if (placement.mode === 'merged') {
    const first = steps.find((s) => s.id === placement.stepId);
    if (first) first.receivedData = input;
  }
  const count = steps.reduce((n, s) => n + 1 + (s.children?.length ?? 0), 0);
  return { steps, stepCount: count, documentInput: !!doc, separateInput: placement.mode === 'separate', input };
}
