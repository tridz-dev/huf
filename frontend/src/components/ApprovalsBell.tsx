import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { approveFlowRun, getPendingApprovals, rejectFlowRun } from '../services/flowApi';
import type { PendingApproval } from '../services/flowApi';
import { useUser } from '../contexts/UserContext';
import { toast } from 'sonner';
import { humanizeFlowError } from '@/lib/flow-graph/flowValidation';
import { formatAbsoluteTime, useSiteTimezone } from '@/lib/serverTime';
import { formatTimeAgo } from '@/utils/time';

const REFRESH_INTERVAL_MS = 60000;
const FLOW_EVENTS = ['frappe:flow_paused', 'frappe:flow_completed', 'frappe:flow_error'];


export function ApprovalsBell() {
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const { isAuthenticated } = useUser();
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

  const handleApprove = async (flowRunId: string) => {
    try {
      await approveFlowRun(flowRunId);
      toast.success('Approved. The flow will continue.');
    } catch (error) {
      toast.error('Could not approve', { description: humanizeFlowError(error) });
    }
    await fetchApprovals();
  };

  const handleReject = async (flowRunId: string) => {
    try {
      await rejectFlowRun(flowRunId);
      toast.success('Rejected. The flow will follow its rejected path.');
    } catch (error) {
      toast.error('Could not reject', { description: humanizeFlowError(error) });
    }
    await fetchApprovals();
  };

  const count = approvals.length;

  return (
    <Popover onOpenChange={(open) => { if (open) void fetchApprovals(); }}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label="Pending approvals" data-testid="flow-approvals-bell">
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
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0" data-testid="flow-approvals-panel">
        <div className="px-4 py-3 border-b text-sm font-semibold">Pending approvals</div>
        {count === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">
            No approvals waiting
          </div>
        ) : (
          <div className="max-h-80 overflow-y-auto divide-y">
            {approvals.map((approval) => (
              <div key={approval.flow_run_id} className="px-4 py-3 space-y-2" data-testid={`flow-approval-${approval.flow_run_id}`}>
                <div>
                  <div className="text-sm font-medium" data-testid={`flow-approval-flow-${approval.flow_run_id}`}>
                    {approval.flow_name || approval.flow_id}
                  </div>
                  {(approval.message || approval.instructions) ? (
                    <div className="text-sm text-foreground mt-0.5" data-testid={`flow-approval-message-${approval.flow_run_id}`}>
                      {approval.message || approval.instructions}
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground mt-0.5">Approval needed</div>
                  )}
                  {approval.waiting_since && (
                    <div className="text-xs text-muted-foreground mt-0.5" data-testid={`flow-approval-time-${approval.flow_run_id}`}>
                      Waiting since {formatAbsoluteTime(approval.waiting_since)} ({formatTimeAgo(approval.waiting_since).toLowerCase()})
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" data-testid={`flow-approve-${approval.flow_run_id}`} onClick={() => handleApprove(approval.flow_run_id)}>
                    Approve
                  </Button>
                  <Button size="sm" variant="outline" data-testid={`flow-reject-${approval.flow_run_id}`} onClick={() => handleReject(approval.flow_run_id)}>
                    Reject
                  </Button>
                  <Button size="sm" variant="ghost" asChild>
                    <Link to={`/flows/${approval.flow_id}?run=${approval.flow_run_id}`}>Open</Link>
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
