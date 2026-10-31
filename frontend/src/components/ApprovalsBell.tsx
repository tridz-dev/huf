import { useCallback, useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { approveFlowRun, getPendingApprovals, rejectFlowRun } from '../services/flowApi';
import type { PendingApproval } from '../services/flowApi';
import { useUser } from '../contexts/UserContext';
import { toast } from 'sonner';
import { humanizeFlowError } from '@/lib/flow-graph/flowValidation';
import { useSiteTimezone } from '@/lib/serverTime';
import { decisionMovedRun } from '@/lib/flow-run/flowRunDecision';
import { ApprovalsList } from './flow/decision/ApprovalsList';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from './ui/sheet';
import { useViewport } from '@/lib/ui/responsive';

const REFRESH_INTERVAL_MS = 60000;
const FLOW_EVENTS = ['frappe:flow_paused', 'frappe:flow_completed', 'frappe:flow_error'];


export function ApprovalsBell() {
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const { isAuthenticated } = useUser();
  const { isPhone } = useViewport();
  const [sheetOpen, setSheetOpen] = useState(false);
  useSiteTimezone();

  const fetchApprovals = useCallback(async () => {
    try {
      const list = await getPendingApprovals();
      setApprovals(list || []);
    } catch (error) {
      console.warn('ApprovalsBell: failed to fetch pending approvals', error);
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    fetchApprovals();
    const interval = setInterval(fetchApprovals, REFRESH_INTERVAL_MS);
    FLOW_EVENTS.forEach((event) => window.addEventListener(event, fetchApprovals));
    return () => {
      clearInterval(interval);
      FLOW_EVENTS.forEach((event) => window.removeEventListener(event, fetchApprovals));
    };
  }, [fetchApprovals, isAuthenticated]);

  // Runs whose decision is on its way: their buttons stay off until the server has answered and the list is read again.
  const [deciding, setDeciding] = useState<Set<string>>(new Set());
  const decidingRef = useRef<Set<string>>(new Set());

  const setBusy = (flowRunId: string, busy: boolean) => {
    const next = new Set(decidingRef.current);
    if (busy) next.add(flowRunId); else next.delete(flowRunId);
    decidingRef.current = next;
    setDeciding(next);
  };

  // The success toast only follows the server's answer that the run moved on; the list is read again either way.
  const decide = async (approval: PendingApproval, decision: 'approve' | 'reject') => {
    const flowRunId = approval.flow_run_id;
    if (decidingRef.current.has(flowRunId)) return;
    setBusy(flowRunId, true);
    const approving = decision === 'approve';
    try {
      const answer = approving ? await approveFlowRun(flowRunId) : await rejectFlowRun(flowRunId);
      if (decisionMovedRun(answer, approval.current_node_id)) {
        toast.success(approving ? 'Approved. The flow will continue.' : 'Rejected. The flow will follow its rejected path.');
      } else {
        toast.error(approving ? 'Could not approve' : 'Could not reject', {
          description: 'The run did not move on, so nothing was recorded. Please try again.',
        });
      }
    } catch (error) {
      toast.error(approving ? 'Could not approve' : 'Could not reject', { description: humanizeFlowError(error) });
    } finally {
      await fetchApprovals();
      setBusy(flowRunId, false);
    }
  };

  const count = approvals.length;
  const trigger = (
    <Button variant="ghost" size="icon" className="relative max-[1023px]:min-h-11 max-[1023px]:min-w-11" aria-label="Pending approvals" data-testid="flow-approvals-bell" onClick={isPhone ? () => { void fetchApprovals(); setSheetOpen(true); } : undefined}>
      <Bell className="w-4 h-4" />
      {count > 0 && (
        <Badge
          variant="destructive"
          className="absolute -top-1 -right-1 h-4 min-w-[16px] px-1 py-0 flex items-center justify-center"
          data-testid="flow-approvals-count"
        >
          {count > 9 ? '9+' : count}
        </Badge>
      )}
    </Button>
  );
  const body = count === 0 ? (
    <div className="px-4 py-6 text-center text-sm text-muted-foreground">No approvals waiting</div>
  ) : (
    <div className="max-h-[min(30rem,70dvh)] overflow-y-auto max-sm:max-h-none">
      <ApprovalsList approvals={approvals} deciding={deciding} onDecide={decide} large={isPhone} onNavigate={() => setSheetOpen(false)} />
    </div>
  );

  // A phone gets a full-width sheet from the bottom; a bigger screen a popover under the bell.
  if (isPhone) {
    return (
      <>
        {trigger}
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetContent side="bottom" className="flex max-h-[85dvh] flex-col gap-0 overflow-hidden rounded-t-xl p-0" data-testid="flow-approvals-panel">
            <SheetHeader className="shrink-0 border-b px-4 py-3 pr-12 text-left">
              <SheetTitle className="text-base">{count > 0 ? `Needs your approval (${count})` : 'Pending approvals'}</SheetTitle>
              <SheetDescription className="sr-only">Runs waiting for your decision.</SheetDescription>
            </SheetHeader>
            <div className="min-h-0 flex-1 overflow-y-auto pb-[env(safe-area-inset-bottom)]">{body}</div>
          </SheetContent>
        </Sheet>
      </>
    );
  }
  return (
    <Popover onOpenChange={(open) => { if (open) void fetchApprovals(); }}>
      <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      <PopoverContent align="end" className="w-[min(360px,calc(100vw-1rem))] p-0" data-testid="flow-approvals-panel">
        <div className="px-4 py-3 border-b text-sm font-semibold">{count > 0 ? `Pending approvals (${count})` : 'Pending approvals'}</div>
        {body}
      </PopoverContent>
    </Popover>
  );
}
