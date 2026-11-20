import { useState } from 'react';
import { toast } from 'sonner';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { reprocessInput, retryIngestion } from '@/services/knowledgeApi';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import type { KnowledgeInputDoc, KnowledgeSourceDoc } from '@/types/knowledge.types';
import { AddContentDialog } from './import/AddContentDialog';
import { DocumentsSummary } from './import/DocumentsSummary';
import { IngestionProblemsSheet } from './import/IngestionProblemsSheet';
import { IngestionProgressCard } from './import/IngestionProgressCard';
import type { DocFilter } from './import/docFilter';
import type { InputCounts } from './import/ingestionLabels';
import { DocumentsTable } from './DocumentsTable';

interface DocumentsTabProps {
  knowledgeSource: string;
  source: KnowledgeSourceDoc;
  inputs: KnowledgeInputDoc[];
  inputsLoading: boolean;
  counts: InputCounts;
  active: string | null;
  latest: string | null;
  addOpen: boolean;
  onAddOpenChange: (open: boolean) => void;
  /** Re-check the active import and counts. */
  onRefreshOverview: () => void;
  /** Refetch source + inputs (never saves the source). */
  onChanged: () => void;
  onReprocess: (name: string) => Promise<void> | void;
  onRemove: (name: string) => Promise<void> | void;
}

export function DocumentsTab({
  knowledgeSource,
  source,
  inputs,
  inputsLoading,
  counts,
  active,
  addOpen,
  onAddOpenChange,
  onRefreshOverview,
  onChanged,
  onReprocess,
  onRemove,
}: DocumentsTabProps) {
  const [shown, setShown] = useState<string | null>(null);
  const [problemsFor, setProblemsFor] = useState<string | null>(null);
  const [filter, setFilter] = useState<DocFilter | null>(null);
  const [retrying, setRetrying] = useState(false);
  const ingestion = shown ?? active;
  const retryAll = async () => {
    setRetrying(true);
    try {
      const failed = inputs.filter((i) => i.status === 'Error');
      const ing = failed.find((i) => i.ingestion)?.ingestion;
      if (ing) {
        await retryIngestion(ing, true);
        setShown(ing);
      } else {
        for (const i of failed) await reprocessInput(i.name);
      }
      toast.success('Retrying failed documents.');
      onRefreshOverview();
      onChanged();
    } catch (e) {
      toast.error(getFrappeErrorMessage(e) || 'Could not retry');
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="documents-tab">
      <DocumentsSummary counts={counts} filter={filter} onFilterChange={setFilter} />

      {counts.failed > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm" data-testid="attention-bar">
          <span>
            {counts.failed.toLocaleString()} {counts.failed === 1 ? 'document needs' : 'documents need'} attention
          </span>
          <Button type="button" size="sm" variant="link" className="h-auto p-0" disabled={retrying} onClick={() => void retryAll()}>
            {retrying ? 'Retrying...' : 'Retry all'}
          </Button>
          <Button type="button" size="sm" variant="link" className="h-auto p-0" onClick={() => setFilter('attention')}>
            Show them
          </Button>
        </div>
      )}

      {source.status === 'Error' && (
        <Alert variant="destructive">
          <AlertDescription>
            Search is unavailable right now. Check Settings, then try Rebuild search index from the menu.
          </AlertDescription>
        </Alert>
      )}

      {ingestion && (
        <IngestionProgressCard
          key={ingestion}
          ingestion={ingestion}
          onViewDetails={setProblemsFor}
          onFinished={() => {
            onRefreshOverview();
            onChanged();
          }}
          onDismiss={() => {
            setShown(null);
            onRefreshOverview();
          }}
        />
      )}

      {counts.total === 0 && !ingestion && !inputsLoading ? (
        <div className="rounded-md border border-dashed py-10 text-center" data-testid="documents-empty">
          <p className="text-sm text-steel">No documents yet. Add your first documents to make this source useful.</p>
          <div className="mt-4 flex justify-center gap-2">
            <Button type="button" size="sm" onClick={() => onAddOpenChange(true)}>
              Upload documents
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => onAddOpenChange(true)}>
              Connect storage
            </Button>
          </div>
        </div>
      ) : (
        <DocumentsTable inputs={inputs} filter={filter} loading={inputsLoading} onReprocess={onReprocess} onRemove={onRemove} />
      )}

      <IngestionProblemsSheet
        ingestion={problemsFor}
        onOpenChange={(o) => !o && setProblemsFor(null)}
        onRetried={() => {
          setShown(problemsFor);
          onRefreshOverview();
        }}
      />

      <AddContentDialog
        open={addOpen}
        onOpenChange={onAddOpenChange}
        knowledgeSource={knowledgeSource}
        sourceLabel={source.source_name}
        onInputAdded={() => {
          onRefreshOverview();
          onChanged();
        }}
        onStarted={(name) => {
          setShown(name);
          onRefreshOverview();
          onChanged();
        }}
      />
    </div>
  );
}
