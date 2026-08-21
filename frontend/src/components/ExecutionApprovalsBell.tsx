import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ShieldAlert } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import {
  approveExecution,
  getPendingExecutionApprovals,
  rejectExecution,
} from '../services/executionApi';
import type { PendingExecutionApproval } from '../services/executionApi';
import { useUser } from '../contexts/UserContext';

const REFRESH_INTERVAL_MS = 60000;
/** Recompute expiry urgency independently of the fetch cycle so the
 * countdown stays fresh while the popover is open. */
const TICK_INTERVAL_MS = 30000;
/** Below this remaining time, an approval is flagged as urgent (24h TTL). */
const URGENT_THRESHOLD_MS = 60 * 60 * 1000;

const EXECUTION_KIND_LABELS: Record<string, string> = {
  code_execution: 'Code execution',
  ssh_exec: 'SSH command',
};

function executionKindLabel(kind: string): string {
  return EXECUTION_KIND_LABELS[kind] || kind.replace(/_/g, ' ');
}

function formatExpiry(expiresOn: string, now: number): { label: string; urgent: boolean; expired: boolean } {
  const expiresAt = new Date(expiresOn).getTime();
  if (Number.isNaN(expiresAt)) {
    return { label: 'Expiry unknown', urgent: false, expired: false };
  }

  const diffMs = expiresAt - now;
  if (diffMs <= 0) {
    return { label: 'Expiring now', urgent: true, expired: true };
  }

  const diffMinutes = Math.round(diffMs / 60000);
  const urgent = diffMs < URGENT_THRESHOLD_MS;

  if (diffMinutes < 60) {
    return { label: `Expires in ${diffMinutes} min`, urgent, expired: false };
  }

  const diffHours = Math.round(diffMs / 3600000);
  if (diffHours < 24) {
    return { label: `Expires in ${diffHours} hr`, urgent, expired: false };
  }

  const diffDays = Math.round(diffMs / 86400000);
  return { label: `Expires in ${diffDays} day${diffDays === 1 ? '' : 's'}`, urgent, expired: false };
}

export function ExecutionApprovalsBell() {
  const [approvals, setApprovals] = useState<PendingExecutionApproval[]>([]);
  const [now, setNow] = useState(() => Date.now());
  const [decidingName, setDecidingName] = useState<string | null>(null);
  const { isAuthenticated } = useUser();

  const fetchApprovals = useCallback(async () => {
    try {
      const list = await getPendingExecutionApprovals();
      setApprovals(list || []);
    } catch (error) {
      console.warn('ExecutionApprovalsBell: failed to fetch pending execution approvals', error);
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    fetchApprovals();
    const interval = setInterval(fetchApprovals, REFRESH_INTERVAL_MS);
    const tick = setInterval(() => setNow(Date.now()), TICK_INTERVAL_MS);
    return () => {
      clearInterval(interval);
      clearInterval(tick);
    };
  }, [fetchApprovals, isAuthenticated]);

  const handleApprove = async (name: string) => {
    setDecidingName(name);
    try {
      await approveExecution(name);
      setApprovals((prev) => prev.filter((approval) => approval.name !== name));
      toast.success('Execution approved');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to approve execution');
    } finally {
      setDecidingName(null);
    }
  };

  const handleReject = async (name: string) => {
    setDecidingName(name);
    try {
      await rejectExecution(name);
      setApprovals((prev) => prev.filter((approval) => approval.name !== name));
      toast.success('Execution rejected');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to reject execution');
    } finally {
      setDecidingName(null);
    }
  };

  const count = approvals.length;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label="Pending execution approvals">
          <ShieldAlert className="w-4 h-4" />
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
        <div className="px-4 py-3 border-b text-sm font-semibold">Pending execution approvals</div>
        {count === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">
            No executions waiting
          </div>
        ) : (
          <div className="max-h-80 overflow-y-auto divide-y">
            {approvals.map((approval) => {
              const expiry = formatExpiry(approval.expires_on, now);
              const deciding = decidingName === approval.name;
              return (
                <div key={approval.name} className="px-4 py-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <Badge variant="pill-neutral">{executionKindLabel(approval.execution_kind)}</Badge>
                    <Badge variant={expiry.urgent ? 'pill-danger' : 'pill-warning'}>
                      {expiry.label}
                    </Badge>
                  </div>
                  <div>
                    <div className="text-sm font-medium">{approval.requested_capability}</div>
                    <div className="text-xs text-muted-foreground">
                      {approval.agent_name ? `${approval.agent_name}` : 'Unknown agent'}
                      {approval.requested_by ? ` · requested by ${approval.requested_by}` : ''}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={deciding}
                      onClick={() => handleApprove(approval.name)}
                    >
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={deciding}
                      onClick={() => handleReject(approval.name)}
                    >
                      Reject
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
