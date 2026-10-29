import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import type { PendingApproval } from '@/services/flowApi';
import { formatAbsoluteTime } from '@/lib/serverTime';
import { formatTimeAgo } from '@/utils/time';
import { humanizeMessageText } from '@/lib/flow-run/humanize';
import { groupApprovals, groupHeading } from '@/lib/flow-run/groupApprovals';
import { cn } from '@/lib/utils';

/** The approval request as a sentence: any data a flow wrote into the message as JSON reads as plain facts. */
export function approvalSentence(approval: PendingApproval): string {
  return humanizeMessageText(approval.message || approval.instructions || '');
}

interface ApprovalsListProps {
  approvals: PendingApproval[];
  deciding: Set<string>;
  onDecide: (approval: PendingApproval, decision: 'approve' | 'reject') => void;
  /** Full-width, 48px buttons (the phone sheet). */
  large?: boolean;
  onNavigate?: () => void;
}

/** What waits for the person's decision: identical requests collapsed under one line, each with Approve, Reject and Open. */
export function ApprovalsList({ approvals, deciding, onDecide, large, onNavigate }: ApprovalsListProps) {
  const groups = groupApprovals(approvals, approvalSentence);
  const button = large ? 'min-h-12 flex-1 text-base' : 'max-[1023px]:min-h-11';
  return (
    <div className="divide-y">
      {groups.map((group) => {
        const heading = groupHeading(group);
        return (
          <div key={group.key} data-testid={`flow-approval-group-${group.items[0].flow_run_id}`} className="px-4 py-3">
            {heading && <div className="mb-1 text-sm font-semibold" data-testid="flow-approval-group-heading">{heading}</div>}
            <div className={cn('space-y-3', heading && 'divide-y [&>*]:pt-3 [&>*:first-child]:pt-0')}>
              {group.items.map((approval) => (
                <div key={approval.flow_run_id} className="space-y-2" data-testid={`flow-approval-${approval.flow_run_id}`}>
                  <div>
                    {!heading && (
                      <div className="text-sm font-medium" data-testid={`flow-approval-flow-${approval.flow_run_id}`}>
                        {approval.flow_name || approval.flow_id}
                      </div>
                    )}
                    {heading && <span className="sr-only" data-testid={`flow-approval-flow-${approval.flow_run_id}`}>{approval.flow_name || approval.flow_id}</span>}
                    {group.sentence ? (
                      <div className={cn('text-sm text-foreground break-words', !heading && 'mt-0.5')} data-testid={`flow-approval-message-${approval.flow_run_id}`}>
                        {group.sentence}
                      </div>
                    ) : (
                      <div className="mt-0.5 text-sm text-muted-foreground">Approval needed</div>
                    )}
                    {approval.waiting_since && (
                      <div className="mt-0.5 text-xs text-muted-foreground" data-testid={`flow-approval-time-${approval.flow_run_id}`}>
                        Waiting since {formatAbsoluteTime(approval.waiting_since)} ({formatTimeAgo(approval.waiting_since).toLowerCase()})
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button size={large ? 'lg' : 'sm'} variant="outline" className={button} disabled={deciding.has(approval.flow_run_id)} data-testid={`flow-approve-${approval.flow_run_id}`} onClick={() => onDecide(approval, 'approve')}>
                      Approve
                    </Button>
                    <Button size={large ? 'lg' : 'sm'} variant="outline" className={button} disabled={deciding.has(approval.flow_run_id)} data-testid={`flow-reject-${approval.flow_run_id}`} onClick={() => onDecide(approval, 'reject')}>
                      Reject
                    </Button>
                    <Button size={large ? 'lg' : 'sm'} variant="ghost" className={large ? 'min-h-12' : 'max-[1023px]:min-h-11'} asChild>
                      <Link to={`/flows/${approval.flow_id}?run=${approval.flow_run_id}`} onClick={onNavigate}>Open</Link>
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
