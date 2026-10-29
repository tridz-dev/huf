import { Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DisabledReason } from '../DisabledReason';
import { cn } from '@/lib/utils';

/** The server's refusal in plain words: "Only people with the Huf User role can approve or reject this one." */
export function whyCannotDecide(reason?: string | null): string {
  const role = reason?.match(/required role '([^']+)'/)?.[1];
  if (role) return `Only people with the ${role} role can approve or reject this one.`;
  if (reason && /System Manager/.test(reason)) return 'Only a system manager can approve or reject this one.';
  if (reason && /not an authorised approver/i.test(reason)) return 'Only the people named for this approval can approve or reject it.';
  return reason || 'Only the people chosen for this approval can approve or reject it.';
}

interface RunDecisionBarProps {
  /** Whether the signed-in person is one of the approvers (the server's own check, sent with the run). */
  canDecide: boolean;
  /** Why not, in the server's words. */
  reason?: string | null;
  busy?: boolean;
  onDecide: (decision: 'approved' | 'rejected') => void;
  /** Stuck to the bottom of a phone sheet: full-width 48px buttons. */
  sticky?: boolean;
}

/**
 * Approve and Reject for a run that waits for a decision. Someone who may not decide is told so, in words, and the buttons stay
 * visible but off with the reason (the server would refuse them anyway, with a toast, after the click).
 */
export function RunDecisionBar({ canDecide, reason, busy, onDecide, sticky }: RunDecisionBarProps) {
  const why = canDecide ? null : whyCannotDecide(reason);
  const size = sticky ? 'min-h-12 flex-1 text-base' : 'max-[1023px]:min-h-11';
  const buttons = (
    <div className={cn('flex items-center gap-3', sticky ? 'w-full' : 'pt-2')}>
      <DisabledReason reason={why}>
        <Button size={sticky ? 'lg' : 'sm'} data-testid="flow-run-approve" disabled={busy} onClick={() => onDecide('approved')} className={cn('gap-2 bg-good text-panel hover:bg-good/90', size)}>
          <Check className="w-4 h-4" /> Approve
        </Button>
      </DisabledReason>
      <DisabledReason reason={why}>
        <Button size={sticky ? 'lg' : 'sm'} variant="outline" data-testid="flow-run-reject" disabled={busy} onClick={() => onDecide('rejected')} className={cn('gap-2 border-destructive text-destructive hover:bg-destructive/10', size)}>
          <X className="w-4 h-4" /> Reject
        </Button>
      </DisabledReason>
    </div>
  );
  return (
    <div
      className={cn(sticky && 'shrink-0 border-t border-line bg-background px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 shadow-[0_-4px_12px_-8px_rgba(0,0,0,0.25)]')}
      data-testid={sticky ? 'flow-run-decision-bar' : 'flow-run-decision-inline'}
    >
      {why && <p className="mb-2 text-sm text-steel" data-testid="flow-run-cannot-decide">{why}</p>}
      {buttons}
    </div>
  );
}
