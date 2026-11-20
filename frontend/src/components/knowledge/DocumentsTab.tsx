import { useState } from 'react';
import { toast } from 'sonner';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { reprocessInput, retryIngestion } from '@/services/knowledgeApi';
import { UploadCloud } from 'lucide-react';
import { cn } from '@/lib/utils';
import { NextStepsCard } from './import/NextStepsCard';
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
  onTryQuestion: () => void;
  onConnectAgent: () => void;
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
  onTryQuestion,
  onConnectAgent,
  onReprocess,
  onRemove,
}: DocumentsTabProps) {
  const [shown, setShown] = useState<string | null>(null);
  const [problemsFor, setProblemsFor] = useState<string | null>(null);
  const [filter, setFilter] = useState<DocFilter | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [armed, setArmed] = useState(false);
  const [dropped, setDropped] = useState<File[]>([]);
  const [addTab, setAddTab] = useState<'upload' | 'storage'>('upload');
  const [dragOver, setDragOver] = useState(false);
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
            setArmed(true);
            onRefreshOverview();
            onChanged();
          }}
          onDismiss={() => {
            setShown(null);
            onRefreshOverview();
          }}
        />
      )}

      {armed && counts.ready > 0 && !ingestion && (
        <NextStepsCard knowledgeSource={knowledgeSource} ready={counts.ready} onTry={onTryQuestion} onConnect={onConnectAgent} />
      )}

      {counts.total === 0 && !ingestion && !inputsLoading ? (
        <div
          className={cn(
            'rounded-md border-2 border-dashed px-6 py-16 text-center transition-colors',
            dragOver ? 'border-primary bg-primary/5' : 'border-input',
          )}
          data-testid="documents-empty"
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            if (e.dataTransfer.files.length === 0) return;
            setDropped(Array.from(e.dataTransfer.files));
            setAddTab('upload');
            onAddOpenChange(true);
          }}
        >
          <UploadCloud className="mx-auto mb-3 h-10 w-10 text-steel-soft" />
          <p className="text-base font-medium">Drop files here to add them</p>
          <p className="mt-1 text-sm text-steel">No documents yet. Add your first documents to make this source useful.</p>
          <div className="mt-5 flex justify-center gap-2">
            <Button
              type="button"
              size="sm"
              onClick={() => {
                setAddTab('upload');
                onAddOpenChange(true);
              }}
            >
              Add content
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                setAddTab('storage');
                onAddOpenChange(true);
              }}
            >
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
        onOpenChange={(o) => {
          if (!o) setDropped([]);
          onAddOpenChange(o);
        }}
        knowledgeSource={knowledgeSource}
        sourceLabel={source.source_name}
        initialTab={addTab}
        initialFiles={dropped}
        onInputAdded={() => {
          setArmed(true);
          onRefreshOverview();
          onChanged();
        }}
        onStarted={(name) => {
          setDropped([]);
          setShown(name);
          onRefreshOverview();
          onChanged();
        }}
      />
    </div>
  );
}
