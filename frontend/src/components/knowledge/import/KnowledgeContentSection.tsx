import { useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useActiveIngestion } from './useIngestionPolling';
import type { KnowledgeInputDoc, KnowledgeSourceDoc } from '@/types/knowledge.types';
import { AddContentDialog } from './AddContentDialog';
import { DocumentsSummary, HealthBadge } from './DocumentsSummary';
import { IngestionProblemsSheet } from './IngestionProblemsSheet';
import { IngestionProgressCard } from './IngestionProgressCard';
import { computeHealth, countInputs } from './ingestionLabels';

interface KnowledgeContentSectionProps {
  knowledgeSource: string;
  source: KnowledgeSourceDoc | null;
  inputs: KnowledgeInputDoc[];
  addOpen: boolean;
  onAddOpenChange: (open: boolean) => void;
  /** Refetch source + inputs (never saves the source). */
  onChanged: () => void;
}

/** Health badge, documents summary, live import progress and the Add content dialog. */
export function KnowledgeContentSection({
  knowledgeSource,
  source,
  inputs,
  addOpen,
  onAddOpenChange,
  onChanged,
}: KnowledgeContentSectionProps) {
  const [bump, setBump] = useState(0);
  const [shown, setShown] = useState<string | null>(null);
  const [problemsFor, setProblemsFor] = useState<string | null>(null);
  const { active, latest } = useActiveIngestion(knowledgeSource, bump);
  const ingestion = shown ?? active;

  const counts = useMemo(() => countInputs(inputs), [inputs]);
  const health = computeHealth(source, counts, !!active);

  if (!source) return null;

  return (
    <section className="space-y-3" data-testid="knowledge-content-section">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <HealthBadge health={health} />
          <DocumentsSummary counts={counts} onReviewProblems={() => setProblemsFor(latestProblemIngestion(inputs) ?? latest)} />
        </div>
        <Button type="button" size="sm" onClick={() => onAddOpenChange(true)} data-testid="add-content">
          <Plus className="mr-2 h-4 w-4" />
          Add content
        </Button>
      </div>

      {source.status === 'Error' && source.error_message && (
        <Alert variant="destructive">
          <AlertDescription>
            Search is unavailable right now. Open the Status tab for details, then try Rebuild search index.
          </AlertDescription>
        </Alert>
      )}

      {counts.total === 0 && !ingestion && (
        <Alert>
          <AlertDescription>
            No documents yet. Add your first documents to make this source useful.
          </AlertDescription>
        </Alert>
      )}

      {ingestion && (
        <IngestionProgressCard
          key={ingestion}
          ingestion={ingestion}
          onViewDetails={setProblemsFor}
          onFinished={() => {
            setBump((b) => b + 1);
            onChanged();
          }}
          onDismiss={() => {
            setShown(null);
            setBump((b) => b + 1);
          }}
        />
      )}

      <IngestionProblemsSheet
        ingestion={problemsFor}
        onOpenChange={(o) => !o && setProblemsFor(null)}
        onRetried={() => {
          setShown(problemsFor);
          setBump((b) => b + 1);
        }}
      />

      <AddContentDialog
        open={addOpen}
        onOpenChange={onAddOpenChange}
        knowledgeSource={knowledgeSource}
        sourceLabel={source.source_name}
        onInputAdded={() => {
          setBump((b) => b + 1);
          onChanged();
        }}
        onStarted={(name) => {
          setShown(name);
          setBump((b) => b + 1);
          onChanged();
        }}
      />
    </section>
  );
}

/** The ingestion that produced the most recent problem rows, falling back to none. */
function latestProblemIngestion(inputs: KnowledgeInputDoc[]): string | null {
  const row = inputs.find(
    (i) => (i.status === 'Error' || (i.status as string) === 'Skipped') && i.ingestion,
  );
  return row?.ingestion ?? null;
}
