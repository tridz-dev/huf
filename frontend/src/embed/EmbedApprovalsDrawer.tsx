import { useCallback, useEffect, useState } from 'react';
import { Check, Loader2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { approveFlowRun, rejectFlowRun } from '@/services/flowApi';
import { toast } from '@/lib/toast';
import { listFlowApprovals, type EmbedApproval } from './embedApi';

interface EmbedApprovalsDrawerProps {
  flowId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Opens the run's trace inside the frame. */
  onOpenRun: (runId: string) => void;
}

/** This flow's runs waiting for the user's decision: approve, or reject with a reason. */
export function EmbedApprovalsDrawer({ flowId, open, onOpenChange, onOpenRun }: EmbedApprovalsDrawerProps) {
  const [rows, setRows] = useState<EmbedApproval[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setFailed(false);
    try {
      setRows(await listFlowApprovals(flowId));
    } catch {
      setFailed(true);
    }
  }, [flowId]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const decide = async (runId: string, approve: boolean) => {
    const reason = (reasons[runId] ?? '').trim();
    if (!approve && !reason) return;
    setBusy(runId);
    try {
      if (approve) await approveFlowRun(runId, reason || undefined);
      else await rejectFlowRun(runId, reason);
      toast.success(approve ? 'Approved' : 'Rejected');
      await load();
    } catch {
      toast.error('Could not record the decision');
    } finally {
      setBusy(null);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex w-full flex-col gap-4 overflow-y-auto sm:max-w-md" data-testid="embed-approvals">
        <SheetHeader>
          <SheetTitle>Waiting for approval</SheetTitle>
          <SheetDescription>Runs of this flow that wait for your decision.</SheetDescription>
        </SheetHeader>
        {rows === null && !failed && <Loader2 className="h-4 w-4 animate-spin" aria-label="Loading" />}
        {failed && (
          <div role="alert" className="grid gap-2 text-sm">
            <p>The approvals could not be loaded.</p>
            <Button size="sm" variant="outline" onClick={() => void load()}>Retry</Button>
          </div>
        )}
        {rows?.length === 0 && <p className="text-sm text-muted-foreground" data-testid="embed-approvals-empty">Nothing is waiting for you.</p>}
        {rows?.map((row) => {
          const reason = reasons[row.flow_run_id] ?? '';
          return (
            <div key={row.flow_run_id} className="grid gap-2 rounded-md border border-line p-3" data-testid="embed-approval-row">
              <p className="text-sm font-medium">{row.title}</p>
              {(row.message || row.instructions) && <p className="text-sm text-muted-foreground">{row.message || row.instructions}</p>}
              <Textarea
                aria-label="Reason"
                placeholder="Reason (needed to reject)"
                value={reason}
                onChange={(e) => setReasons((r) => ({ ...r, [row.flow_run_id]: e.target.value }))}
              />
              <div className="flex flex-wrap gap-2">
                <Button size="sm" className="gap-1" data-testid="embed-approve" disabled={busy !== null} onClick={() => void decide(row.flow_run_id, true)}>
                  <Check className="h-4 w-4" /> Approve
                </Button>
                <Button size="sm" variant="outline" className="gap-1" data-testid="embed-reject" disabled={busy !== null || !reason.trim()} onClick={() => void decide(row.flow_run_id, false)}>
                  <X className="h-4 w-4" /> Reject
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onOpenRun(row.flow_run_id)}>See the run</Button>
              </div>
            </div>
          );
        })}
      </SheetContent>
    </Sheet>
  );
}
