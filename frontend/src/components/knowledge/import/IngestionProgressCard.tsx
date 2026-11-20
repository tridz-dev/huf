import { useState } from 'react';
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { useIngestionPolling, isActiveIngestion } from './useIngestionPolling';
import { cancelIngestion, type IngestionStatusResult } from '@/services/knowledgeApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { ConfirmActionDialog } from './ConfirmActionDialog';
import { ingestionStatusLabel } from './ingestionLabels';

interface IngestionProgressCardProps {
  ingestion: string;
  onFinished?: (result: IngestionStatusResult) => void;
  onViewDetails: (ingestion: string) => void;
  onDismiss?: () => void;
}

export function IngestionProgressCard({
  ingestion,
  onFinished,
  onViewDetails,
  onDismiss,
}: IngestionProgressCardProps) {
  const { data, error, refresh, lostMessage } = useIngestionPolling(ingestion, onFinished);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  if (!data) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-4 text-sm text-steel">
          {!lostMessage && <Loader2 className="h-4 w-4 animate-spin" />}
          {lostMessage ?? error ?? 'Loading import progress...'}
        </CardContent>
      </Card>
    );
  }

  const { counts, ingestion: header } = data;
  const status = header.status;
  const active = isActiveIngestion(status);
  const percent = Math.round((data.progress || 0) * 100);
  const done = counts.indexed + counts.error + counts.skipped;
  const scanning = status === 'Scanning';
  const problems = counts.error + counts.skipped;

  const doCancel = async () => {
    setCancelling(true);
    try {
      await cancelIngestion(ingestion);
      toast.success('Import stopped. Files already indexed stay.');
      setConfirmOpen(false);
      await refresh();
    } catch (e) {
      toast.error(getFrappeErrorMessage(e) || 'Could not stop the import');
    } finally {
      setCancelling(false);
    }
  };

  if (!active) {
    const failed = status === 'Failed';
    return (
      <Alert variant={failed || counts.error > 0 ? 'destructive' : 'default'} data-testid="ingestion-done">
        {failed ? <XCircle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
        <AlertTitle>{ingestionStatusLabel(status)}</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>
            {counts.indexed} {counts.indexed === 1 ? 'file' : 'files'} added
            {counts.error > 0 ? `, ${counts.error} failed` : ''}
            {counts.skipped > 0 ? `, ${counts.skipped} skipped` : ''}.
            {failed && header.error_message ? ` ${header.error_message}` : ''}
          </p>
          <div className="flex gap-2">
            {problems > 0 && (
              <Button type="button" size="sm" variant="outline" onClick={() => onViewDetails(ingestion)}>
                Review
              </Button>
            )}
            {onDismiss && (
              <Button type="button" size="sm" variant="ghost" onClick={onDismiss}>
                Dismiss
              </Button>
            )}
          </div>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <Card data-testid="ingestion-progress">
      <CardContent className="space-y-3 py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm">
            <span className="font-medium">
              {scanning || counts.total === 0 ? 'Finding files…' : `Preparing ${done} of ${counts.total}`}
            </span>
          </div>
          <Button type="button" size="sm" variant="outline" onClick={() => setConfirmOpen(true)} data-testid="ingestion-cancel">
            Cancel
          </Button>
        </div>
        {scanning || counts.total === 0 ? (
          <Progress value={100} className="animate-pulse" data-testid="ingestion-indeterminate" />
        ) : (
          <Progress value={percent} />
        )}
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-steel">
          <span>
            {[
              counts.indexed > 0 ? `${counts.indexed} ready` : '',
              counts.skipped > 0 ? `${counts.skipped} skipped` : '',
              counts.error > 0 ? `${counts.error} failed` : '',
              lostMessage ?? '',
            ]
              .filter(Boolean)
              .join(' · ')}
          </span>
          <Button type="button" size="sm" variant="ghost" onClick={() => onViewDetails(ingestion)}>
            View details
          </Button>
        </div>
      </CardContent>
      <ConfirmActionDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Stop this import?"
        description="Files already indexed stay. Files not yet read are left out."
        confirmLabel="Stop import"
        cancelLabel="Keep going"
        destructive
        busy={cancelling}
        onConfirm={doCancel}
      />
    </Card>
  );
}
