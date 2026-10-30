import type { FlowRunDetail } from '@/services/flowApi';
import { formatDuration, friendlyClock, runDuration, spokenDuration, sinceMs } from './time';
import { stoppedByPerson } from './runStatus';

export interface RunHeadlineText {
  /** The one sentence a person reads first. */
  headline: string;
  /** A smaller line under it, or ''. */
  sub: string;
}

/** How long a Queued or Running run has been unchanged, in ms (0 when it is not stuck). */
export function stuckMs(run: Pick<FlowRunDetail, 'stale' | 'modified_at' | 'started_at'>, now: number = Date.now()): number {
  return run.stale ? sinceMs(run.modified_at ?? run.started_at, now) : 0;
}

/** The outcome sentence of a run, per state. */
export function runHeadline(run: FlowRunDetail, now: number = Date.now()): RunHeadlineText {
  const status = run.status;
  if (run.stale) return { headline: `Stuck for ${spokenDuration(stuckMs(run, now))}`, sub: 'Nothing has changed since then.' };
  if (status === 'Success') {
    const took = runDuration(run.started_at, run.completed_at);
    if (run.outcome) return { headline: run.outcome.label, sub: took ? `Run finished in ${took}` : 'Run finished' };
    return { headline: took ? `Finished in ${took}` : 'Finished', sub: '' };
  }
  if (status === 'Failed') {
    const by = stoppedByPerson(run.last_error);
    if (by) return { headline: `Stopped by ${by.by}`, sub: by.why };
    return { headline: 'This run stopped because a step failed', sub: '' };
  }
  if (status === 'Waiting Approval') return { headline: 'Waiting for approval', sub: run.started_at ? `Since ${friendlyClock(run.modified_at ?? run.started_at)}` : '' };
  if (status === 'Waiting Code') return { headline: 'Waiting for a code review', sub: 'It continues by itself once the code has been approved.' };
  if (status === 'Waiting User') return { headline: 'Waiting for someone to continue it', sub: '' };
  if (status === 'Queued') return { headline: 'Waiting for a worker', sub: 'It is in line and starts as soon as a worker is free.' };
  const took = run.started_at ? formatDuration(sinceMs(run.started_at, now)) : '';
  return { headline: 'Running now', sub: took ? `Started ${took} ago` : '' };
}

/** "Started by you · 5:15 PM", or "Started by a webhook · Oct 29, 5:15 PM". */
export function startedLine(startedBy: string, startedAt: string | null | undefined): string {
  const when = friendlyClock(startedAt);
  return when ? `Started by ${startedBy} · ${when}` : `Started by ${startedBy}`;
}

/** "Google Sheets" from "Google Sheets is not connected. ...", else undefined. */
export function notConnectedName(reason: string | null | undefined): string | undefined {
  return /^(.+?) is not connected[.:]/.exec(reason ?? '')?.[1];
}
