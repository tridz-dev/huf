import { useState } from 'react';
import { AlertTriangle, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  AlertDialog, AlertDialogCancel, AlertDialogAction, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { spokenDuration } from '@/lib/flow-run/story/time';
import { stuckMs } from '@/lib/flow-run/story/headline';
import type { FlowRunDetail } from '@/services/flowApi';

interface RunStatusBannerProps {
  run: FlowRunDetail;
  /** May edit flows: can cancel a queued run. */
  canManage: boolean;
  onStop: () => void;
  onCancel: () => void;
}

/** A stuck run says for how long and can be stopped; a queued run says it is waiting for a worker and can be cancelled. */
export function RunStatusBanner({ run, canManage, onStop, onCancel }: RunStatusBannerProps) {
  const [confirm, setConfirm] = useState<'stop' | 'cancel' | null>(null);
  const stuck = run.stale;
  const queued = run.status === 'Queued' && !stuck;
  if (!stuck && !queued) return null;
  const flow = run.flow_name || 'this flow';
  return (
    <>
      {stuck ? (
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
            {canManage && (
              <Button size="sm" variant="outline" className="mt-3 max-[1023px]:min-h-11" data-testid="flow-run-cancel" onClick={() => setConfirm('cancel')}>
                Cancel run
              </Button>
            )}
          </div>
        </div>
      )}
      <AlertDialog open={confirm !== null} onOpenChange={(open) => !open && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirm === 'cancel' ? 'Cancel this run?' : 'Stop this run?'}</AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === 'cancel'
                ? `This run of ${flow} has not started yet. Cancelling means it never will.`
                : `This ends the run of ${flow} now and records it as stopped. It cannot be undone.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{confirm === 'cancel' ? 'Keep it' : 'Keep waiting'}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="flow-run-mark-failed-confirm"
              onClick={() => { const which = confirm; setConfirm(null); if (which === 'cancel') onCancel(); else onStop(); }}
            >
              {confirm === 'cancel' ? 'Cancel run' : 'Stop run'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
