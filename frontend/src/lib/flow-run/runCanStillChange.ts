/** True while a stored run status can still move on by itself: Queued, Running, or any Waiting status (approval, code review, reply). */
export function runCanStillChange(status: string | null | undefined): boolean {
  return status === 'Queued' || status === 'Running' || !!status?.startsWith('Waiting');
}
