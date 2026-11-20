import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ProgressRow } from '@/components/patterns';
import { ConfirmActionDialog } from '../import/ConfirmActionDialog';
import { useIngestionPolling, isActiveIngestion } from '../import/useIngestionPolling';
import { ingestionOrigin } from '../import/ingestionOrigin';
import { cancelIngestion, type IngestionStatusResult } from '@/services/knowledgeApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

export interface ImportSummary {
  label: string;
  done: number;
  total: number;
}

export interface SourceImportProgressProps {
  ingestion: string;
  onFinished: (result: IngestionStatusResult) => void;
  onViewDetails: (ingestion: string) => void;
  onProgress?: (summary: ImportSummary | null) => void;
}

/** Live status for the page header. Null when nothing is running. total 0 = still finding files. */
export function importSummary(data: IngestionStatusResult | null | undefined): ImportSummary | null {
  if (!data || !isActiveIngestion(data.ingestion.status)) return null;
  const { counts, ingestion: header } = data;
  if (header.status === 'Scanning' || counts.total === 0) {
    return { label: 'Finding files', done: header.total_items, total: 0 };
  }
  return { label: 'Importing', done: counts.indexed + counts.error + counts.skipped, total: counts.total };
}

export function SourceImportProgress({ ingestion, onFinished, onViewDetails, onProgress }: SourceImportProgressProps) {
  const { data, refresh, lostMessage } = useIngestionPolling(ingestion, onFinished);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const summary = importSummary(data);
  const label = summary?.label;
  const done = summary?.done;
  const total = summary?.total;
  useEffect(() => {
    onProgress?.(label === undefined ? null : { label, done: done ?? 0, total: total ?? 0 });
  }, [label, done, total, onProgress]);

  if (lostMessage) return <p className="px-4 py-3 text-ui-text text-steel">{lostMessage}</p>;
  if (!data || !summary) return null;

  const problems = data.counts.error + data.counts.skipped;
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

  return (
    <>
      <ProgressRow
        label={summary.label}
        source={ingestionOrigin(data.ingestion) || undefined}
        done={summary.done}
        total={summary.total || undefined}
        noun="files"
        onCancel={() => setConfirmOpen(true)}
        secondary={problems > 0 ? { label: 'View details', onClick: () => onViewDetails(ingestion) } : undefined}
      />
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
    </>
  );
}
