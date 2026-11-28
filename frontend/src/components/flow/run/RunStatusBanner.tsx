import { useState } from 'react';
import { AlertTriangle, Clock, Hourglass } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  AlertDialog, AlertDialogCancel, AlertDialogAction, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { DisabledReason } from '@/components/flow/DisabledReason';
import { spokenDuration } from '@/lib/flow-run/story/time';
import { stuckMs } from '@/lib/flow-run/story/headline';
import type { FlowRunDetail } from '@/services/flowApi';

interface RunStatusBannerProps {
  run: FlowRunDetail;
  /** May edit flows: can cancel a queued run. */
  canManage: boolean;
  onStop: () => void;
  onCancel: () => void;
  /** Waiting Timer only: skip the rest of the wait. */
  onContinue?: () => void;
  /** Resume-link waits only: copy the run's single-use resume link. */
  onCopyResumeLink?: () => void;
}

const CANCEL_DENIED = 'Only people who can edit this flow can cancel its runs.';

/** What a run parked on a Wait step is waiting for, in the viewer's time zone. */
function waitingWords(run: FlowRunDetail): string {
  const at = typeof run.waiting?.resume_at === 'string' ? new Date(`${run.waiting.resume_at}Z`) : null;
  if (at && !Number.isNaN(at.getTime())) return `Waiting until ${at.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}.`;
  return 'Waiting for someone to continue it.';
}

/**
 * A waiting run says what it waits for and can be cancelled (and, on a timer, continued now); a stuck run says for how
 * long and can be stopped; a queued run says it is waiting for a worker and can be cancelled.
 */
export function RunStatusBanner({ run, canManage, onStop, onCancel, onContinue, onCopyResumeLink }: RunStatusBannerProps) {
  const [confirm, setConfirm] = useState<'stop' | 'cancel' | 'continue' | null>(null);
  const waiting = run.status.startsWith('Waiting');
  const stuck = run.stale && !waiting;
  const queued = run.status === 'Queued' && !stuck;
  if (!stuck && !queued && !waiting) return null;
  const flow = run.flow_name || 'this flow';
  const extra = (run.waiting?.extra ?? {}) as Record<string, unknown>;
  const resumeLink = run.status === 'Waiting Timer' && extra.mode === 'resume' && extra.wait_for === 'token';
  return (
    <>
      {waiting ? (
        <div className="flex items-start gap-3 rounded-lg border border-line bg-paper-deep p-4" data-testid="flow-run-waiting">
          <Hourglass className="mt-0.5 h-4 w-4 shrink-0 text-steel" aria-hidden />
          <div className="min-w-0 flex-1 text-sm">
            {run.status === 'Waiting Timer' && <p className="text-ink" data-testid="flow-run-waiting-until">{waitingWords(run)}</p>}
            <div className="mt-3 flex flex-wrap gap-2">
              {run.status === 'Waiting Timer' && onContinue && (
                <DisabledReason reason={canManage ? null : 'Only people who can edit this flow can continue its runs.'}>
                  <Button size="sm" variant="outline" className="max-[1023px]:min-h-11" data-testid="flow-run-continue" onClick={() => setConfirm('continue')}>
                    Continue now
                  </Button>
                </DisabledReason>
              )}
              {resumeLink && onCopyResumeLink && (
                <DisabledReason reason={canManage ? null : 'Only people who can edit this flow can see its resume link.'}>
                  <Button size="sm" variant="outline" className="max-[1023px]:min-h-11" data-testid="flow-run-copy-resume-link" title="Anyone with this link can continue the run once." onClick={onCopyResumeLink}>
                    Copy resume link
                  </Button>
                </DisabledReason>
              )}
              <DisabledReason reason={canManage ? null : CANCEL_DENIED}>
                <Button size="sm" variant="outline" className="border-destructive text-destructive hover:bg-destructive/10 max-[1023px]:min-h-11" data-testid="flow-run-cancel" onClick={() => setConfirm('cancel')}>
                  Cancel run
                </Button>
              </DisabledReason>
            </div>
          </div>
        </div>
      ) : stuck ? (
        <div className="flex items-start gap-3 rounded-lg border border-warning/40 bg-warning-tint/50 p-4" data-testid="flow-run-stale">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
          <div className="min-w-0 flex-1 text-sm">
            <p className="text-ink" data-testid="flow-run-stuck-for">
              It is {run.status === 'Queued' ? 'still waiting to start' : 'still running'}, but nothing has changed in {spokenDuration(stuckMs(run))}. If it is not coming back, you can stop it.
              {run.can_mark_failed ? '' : ' A system manager can stop it.'}
            </p>
            {run.can_mark_failed && (
              <Button size="sm" variant="outline" className="mt-3 border-destructive text-destructive hover:bg-destructive/10 max-[1023px]:min-h-11" data-testid="flow-run-mark-failed" onClick={() => setConfirm('stop')}>
                Stop run
              </Button>
            )}
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-3 rounded-lg border border-line bg-paper-deep p-4" data-testid="flow-run-queued">
          <Clock className="mt-0.5 h-4 w-4 shrink-0 text-steel" aria-hidden />
          <div className="min-w-0 flex-1 text-sm">
            <p className="text-ink">You do not need to do anything. If you no longer want this run, you can cancel it.</p>
            <div className="mt-3">
              <DisabledReason reason={canManage ? null : CANCEL_DENIED}>
                <Button size="sm" variant="outline" className="max-[1023px]:min-h-11" data-testid="flow-run-cancel" onClick={() => setConfirm('cancel')}>
                  Cancel run
                </Button>
              </DisabledReason>
            </div>
          </div>
        </div>
      )}
      <AlertDialog open={confirm !== null} onOpenChange={(open) => !open && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirm === 'cancel' ? 'Cancel this run?' : confirm === 'continue' ? 'Continue now?' : 'Stop this run?'}</AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === 'cancel'
                ? (waiting ? 'It stops where it is and will not continue. Steps that already ran are not undone.' : `This run of ${flow} has not started yet. Cancelling means it never will.`)
                : confirm === 'continue'
                ? 'The flow skips the rest of the wait.'
                : `This ends the run of ${flow} now and records it as stopped. It cannot be undone.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{confirm === 'cancel' ? 'Keep it' : confirm === 'continue' ? 'Not yet' : 'Keep waiting'}</AlertDialogCancel>
            <AlertDialogAction
              className={confirm === 'continue' ? undefined : 'bg-destructive text-destructive-foreground hover:bg-destructive/90'}
              data-testid="flow-run-mark-failed-confirm"
              onClick={() => { const which = confirm; setConfirm(null); if (which === 'cancel') onCancel(); else if (which === 'continue') onContinue?.(); else onStop(); }}
            >
              {confirm === 'cancel' ? 'Cancel run' : confirm === 'continue' ? 'Continue now' : 'Stop run'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
