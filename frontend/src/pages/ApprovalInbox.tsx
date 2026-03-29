import { useState, useEffect } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Textarea } from '@/components/ui/textarea';
import { PageLayout } from '@/components/dashboard';
import { Loader2, CheckCircle2, XCircle, Inbox } from 'lucide-react';
import { getPendingApprovals, approveFlowRun, rejectFlowRun, type PendingApproval } from '@/services/flowApi';
import { toast } from 'sonner';

export function ApprovalInbox() {
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);

  useEffect(() => {
    loadApprovals();
  }, []);

  const loadApprovals = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await getPendingApprovals(50);
      setApprovals(result || []);
    } catch (err) {
      setError('Failed to load approvals');
      toast.error('Failed to load approvals');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (flowRunId: string, comments: string = '') => {
    try {
      setProcessingId(flowRunId);
      await approveFlowRun(flowRunId, comments);
      toast.success('Approval successful');
      await loadApprovals();
    } catch (err) {
      setError('Failed to approve');
      toast.error('Failed to approve');
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (flowRunId: string, comments: string = '') => {
    try {
      setProcessingId(flowRunId);
      await rejectFlowRun(flowRunId, comments);
      toast.success('Rejection successful');
      await loadApprovals();
    } catch (err) {
      setError('Failed to reject');
      toast.error('Failed to reject');
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <PageLayout subtitle="Review and approve pending workflow steps">
      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : approvals.length === 0 ? (
        <Card className="p-12">
          <CardContent className="flex flex-col items-center justify-center text-center pt-6">
            <Inbox className="h-16 w-16 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium">No pending approvals</h3>
            <p className="text-muted-foreground mt-2">
              You don&apos;t have any workflows waiting for your approval.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {approvals.map((approval) => (
            <ApprovalCard
              key={approval.flow_run_id}
              approval={approval}
              onApprove={handleApprove}
              onReject={handleReject}
              isProcessing={processingId === approval.flow_run_id}
            />
          ))}
        </div>
      )}
    </PageLayout>
  );
}

interface ApprovalCardProps {
  approval: PendingApproval;
  onApprove: (id: string, comments: string) => void;
  onReject: (id: string, comments: string) => void;
  isProcessing: boolean;
}

function ApprovalCard({ approval, onApprove, onReject, isProcessing }: ApprovalCardProps) {
  const [comments, setComments] = useState('');
  const [showActions, setShowActions] = useState(false);

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-6">
        <div className="flex justify-between items-start gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-2">
              <h3 className="font-semibold text-lg">{approval.title}</h3>
              {approval.approver_role && (
                <Badge variant="secondary">Role: {approval.approver_role}</Badge>
              )}
              {!approval.can_approve && (
                <Badge variant="outline" className="text-amber-600">View Only</Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground mb-2">{approval.flow_name}</p>
            <p className="text-sm mb-3">{approval.instructions}</p>
            <p className="text-xs text-muted-foreground">
              Created: {new Date(approval.created_at).toLocaleString()}
            </p>
          </div>

          <div className="shrink-0">
            {!showActions ? (
              <Button 
                onClick={() => setShowActions(true)}
                disabled={isProcessing || !approval.can_approve}
              >
                Review
              </Button>
            ) : (
              <div className="space-y-3 min-w-[300px]">
                <Textarea
                  value={comments}
                  onChange={(e) => setComments(e.target.value)}
                  placeholder="Comments (optional)"
                  rows={2}
                  disabled={isProcessing}
                />
                <div className="flex gap-2 justify-end">
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() => onApprove(approval.flow_run_id, comments)}
                    disabled={isProcessing}
                  >
                    {isProcessing ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 mr-1" />
                    )}
                    Approve
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => onReject(approval.flow_run_id, comments)}
                    disabled={isProcessing}
                  >
                    {isProcessing ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    ) : (
                      <XCircle className="h-4 w-4 mr-1" />
                    )}
                    Reject
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowActions(false)}
                    disabled={isProcessing}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
