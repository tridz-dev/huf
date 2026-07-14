import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { approveFlowRun, getPendingApprovals, rejectFlowRun } from '../services/flowApi';
import type { PendingApproval } from '../services/flowApi';

const REFRESH_INTERVAL_MS = 60000;
const FLOW_EVENTS = ['frappe:flow_paused', 'frappe:flow_completed', 'frappe:flow_error'];

export function ApprovalsBell() {
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);

  const fetchApprovals = useCallback(async () => {
    try {
      const list = await getPendingApprovals();
      setApprovals(list || []);
    } catch (error) {
      console.warn('ApprovalsBell: failed to fetch pending approvals', error);
    }
  }, []);

  useEffect(() => {
    fetchApprovals();
    const interval = setInterval(fetchApprovals, REFRESH_INTERVAL_MS);
    FLOW_EVENTS.forEach((event) => window.addEventListener(event, fetchApprovals));
    return () => {
      clearInterval(interval);
      FLOW_EVENTS.forEach((event) => window.removeEventListener(event, fetchApprovals));
    };
  }, [fetchApprovals]);

  const handleApprove = async (flowRunId: string) => {
    try {
      await approveFlowRun(flowRunId);
    } catch (error) {
      console.warn('ApprovalsBell: failed to approve flow run', error);
    }
    await fetchApprovals();
  };

  const handleReject = async (flowRunId: string) => {
    try {
      await rejectFlowRun(flowRunId);
    } catch (error) {
      console.warn('ApprovalsBell: failed to reject flow run', error);
    }
    await fetchApprovals();
  };

  const count = approvals.length;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label="Pending approvals">
          <Bell className="w-4 h-4" />
          {count > 0 && (
            <Badge
              variant="destructive"
              className="absolute -top-1 -right-1 h-4 min-w-[16px] px-1 py-0 flex items-center justify-center"
            >
              {count > 9 ? '9+' : count}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="px-4 py-3 border-b text-sm font-semibold">Pending approvals</div>
        {count === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">
            No approvals waiting
          </div>
        ) : (
          <div className="max-h-80 overflow-y-auto divide-y">
            {approvals.map((approval) => (
              <div key={approval.flow_run_id} className="px-4 py-3 space-y-2">
                <div>
                  <div className="text-sm font-medium">{approval.title || approval.flow_id}</div>
                  <div className="text-xs text-muted-foreground">
                    {approval.flow_id}
                    {approval.waiting_since ? ` · waiting since ${approval.waiting_since}` : ''}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => handleApprove(approval.flow_run_id)}>
                    Approve
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => handleReject(approval.flow_run_id)}>
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
