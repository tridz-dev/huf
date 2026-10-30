import type { StatusKind } from '@/components/common/StatusPill';

/** The stored run status plus whether the run looks stuck. */
export interface RunStatusInput {
  status: string | null | undefined;
  stale?: boolean;
}

export interface RunStatusPill {
  kind: StatusKind;
  /** Only where the shared word does not fit (a run waiting for someone to continue it). */
  label?: string;
}

/** A stored run status in the one status set: Queued, Running, Waiting..., Finished, Failed, Stuck. */
export function runStatusPill({ status, stale }: RunStatusInput): RunStatusPill {
  if (stale && (status === 'Queued' || status === 'Running')) return { kind: 'stuck' };
  switch (status) {
    case 'Success':
      return { kind: 'finished' };
    case 'Failed':
      return { kind: 'failed' };
    case 'Queued':
      return { kind: 'queued' };
    case 'Waiting Approval':
      return { kind: 'waiting_approval' };
    case 'Waiting Code':
      return { kind: 'waiting_review' };
    case 'Waiting User':
      return { kind: 'waiting_approval', label: 'Waiting for your reply' };
    default:
      return { kind: 'running' };
  }
}

/** Status filter words, in the order of the status set. The values are the stored statuses. */
export const RUN_STATUS_FILTERS = [
  { label: 'All statuses', value: 'all' },
  { label: 'Queued', value: 'Queued' },
  { label: 'Running', value: 'Running' },
  { label: 'Waiting for approval', value: 'Waiting Approval' },
  { label: 'Waiting for your reply', value: 'Waiting User' },
  { label: 'Waiting for code review', value: 'Waiting Code' },
  { label: 'Finished', value: 'Success' },
  { label: 'Failed', value: 'Failed' },
];

/** A run that can still change on its own (so the lists keep refreshing). */
export const isFinishedStatus = (status: string | null | undefined) => status === 'Success' || status === 'Failed' || status === 'Cancelled';

/** "you" for the signed-in person, else the name or address as recorded. */
export const whoWords = (by: string, currentUser?: string | null) => (currentUser && by === currentUser ? 'you' : by);

/** Whether a stopped run was ended by a person ("Marked as failed by ..." / "Cancelled by ...") rather than failing by itself. */
export function stoppedByPerson(lastError: string | null | undefined): { by: string; why: string } | null {
  const text = (lastError ?? '').trim();
  const cancelled = /^Cancelled by (.+?) before it started\.?$/s.exec(text);
  if (cancelled) return { by: cancelled[1], why: 'It was cancelled before it started.' };
  const stopped = /^(?:Marked as failed|Stopped) by (.+?): the run was stuck in (\w+)\.?$/s.exec(text);
  if (stopped) return { by: stopped[1], why: `It had been stuck while ${stopped[2].toLowerCase()} and was ended by hand.` };
  return null;
}
