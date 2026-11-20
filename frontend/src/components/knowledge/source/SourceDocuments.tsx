import { useState, type ReactNode } from 'react';
import { Cloud, ExternalLink, Loader2, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  AttentionBanner,
  DropZone,
  OverflowMenu,
  ResourceList,
  ResourceListSlot,
  ResourceRow,
  StepHint,
} from '@/components/patterns';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { reprocessInput, retryIngestion } from '@/services/knowledgeApi';
import { formatTimeAgo } from '@/utils/time';
import type { KnowledgeInputDoc } from '@/types/knowledge.types';
import { DocumentDetailSheet } from '../DocumentDetailSheet';
import { inputOrigin, inputTitle } from '../DocumentsTable';
import { ConfirmActionDialog } from '../import/ConfirmActionDialog';
import { DOC_FILTER_STATUS, type SourceFilter } from '../import/docFilter';
import { itemReason, itemStatusLabel, type InputCounts } from '../import/ingestionLabels';

const STEPS = [
  { title: 'Add documents', description: 'Files, web pages or storage' },
  { title: 'Try a question', description: 'See what your agents would find' },
  { title: 'Connect to an agent', description: 'Let an agent use it' },
];
const ACCEPT = '.pdf,.docx,.md,.txt,.csv,.zip';

export interface SourceDocumentsProps {
  knowledgeSource: string;
  inputs: KnowledgeInputDoc[];
  loading: boolean;
  counts: InputCounts;
  filter: SourceFilter;
  onFilterChange: (f: SourceFilter) => void;
  /** Rendered first inside the list (the import progress row). */
  slot?: ReactNode;
  onAddContent: (tab: 'upload' | 'storage') => void;
  onFiles: (files: File[]) => void;
  onRetried: (ingestion?: string) => void;
  onReprocess: (name: string) => Promise<void> | void;
  onRemove: (name: string) => Promise<void> | void;
}

function typeOf(i: KnowledgeInputDoc): string {
  if (i.input_type === 'URL') return 'url';
  if (i.input_type === 'Text') return 'txt';
  const m = /\.([a-z0-9]{1,5})$/i.exec(inputTitle(i));
  return m ? m[1].toLowerCase() : 'file';
}

function StatusPill({ status }: { status: string }) {
  if (status === 'Indexed') return <Badge variant="pill-success">{itemStatusLabel('Indexed')}</Badge>;
  if (status === 'Pending' || status === 'Processing')
    return (
      <Badge variant="pill-info">
        <Loader2 className="mr-1 h-3 w-3 animate-spin" aria-hidden="true" />
        Adding…
      </Badge>
    );
  if (status === 'Error') return <Badge variant="pill-warning">Needs attention</Badge>;
  return <Badge variant="pill-neutral">{status}</Badge>;
}

export function SourceDocuments({
  inputs,
  loading,
  counts,
  filter,
  onFilterChange,
  slot,
  onAddContent,
  onFiles,
  onRetried,
  onReprocess,
  onRemove,
}: SourceDocumentsProps) {
  const [retrying, setRetrying] = useState(false);
  const [openName, setOpenName] = useState<string | null>(null);
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);

  const retryAll = async () => {
    setRetrying(true);
    try {
      const failed = inputs.filter((i) => i.status === 'Error');
      const ing = failed.find((i) => i.ingestion)?.ingestion;
      if (ing) await retryIngestion(ing, true);
      else for (const i of failed) await reprocessInput(i.name);
      toast.success('Retrying failed documents.');
      onRetried(ing || undefined);
    } catch (e) {
      toast.error(getFrappeErrorMessage(e) || 'Could not retry');
    } finally {
      setRetrying(false);
    }
  };

  const retryOne = async (name: string) => {
    try {
      await onReprocess(name);
    } catch (e) {
      toast.error(getFrappeErrorMessage(e) || 'Could not retry');
    }
  };

  if (counts.total === 0 && !loading && !slot) {
    return (
      <div className="space-y-6" data-testid="documents-empty">
        <StepHint current={0} steps={STEPS} />
        <DropZone
          title="Drop files here to add them"
          hint="PDF, Word, Markdown, text and CSV. Up to 50 MB each."
          accept={ACCEPT}
          onFiles={onFiles}
          actions={
            <>
              <Button type="button" size="sm" onClick={() => onAddContent('upload')}>
                <Plus className="mr-2 h-4 w-4" />
                Add content
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={() => onAddContent('storage')}>
                <Cloud className="mr-2 h-4 w-4" />
                Connect storage
              </Button>
            </>
          }
        />
      </div>
    );
  }

  const rows = filter === 'all' ? inputs : inputs.filter((i) => i.status === DOC_FILTER_STATUS[filter]);

  return (
    <>
      <ResourceList label="Documents">
        {slot}
        {counts.failed > 0 && (
          <ResourceListSlot>
            <AttentionBanner
              count={counts.failed}
              message={`${counts.failed.toLocaleString()} documents could not be added.`}
              action={{ label: 'Retry all', onClick: () => void retryAll(), busy: retrying }}
              secondary={{ label: 'Show them', onClick: () => onFilterChange('attention') }}
            />
          </ResourceListSlot>
        )}
        {loading && inputs.length === 0
          ? [0, 1, 2].map((n) => (
              <ResourceListSlot key={n}>
                <Skeleton className="m-3 h-8 w-auto" />
              </ResourceListSlot>
            ))
          : rows.map((i) => {
              const adding = i.status === 'Pending' || i.status === 'Processing';
              const title = inputTitle(i);
              return (
                <ResourceRow
                  key={i.name}
                  type={typeOf(i)}
                  title={title}
                  origin={inputOrigin(i).label}
                  status={<StatusPill status={i.status} />}
                  time={formatTimeAgo(i.creation)}
                  adding={adding}
                  reason={
                    i.status === 'Error' ? (
                      <>
                        {itemReason(i)}{' '}
                        <Button type="button" variant="link" size="sm" onClick={() => void retryOne(i.name)}>
                          Retry
                        </Button>
                      </>
                    ) : i.status === 'Skipped' ? (
                      itemReason(i)
                    ) : undefined
                  }
                  onOpen={() => setOpenName(i.name)}
                  actions={
                    <OverflowMenu
                      size="icon-sm"
                      label={`More actions for ${title}`}
                      items={[
                        { label: 'Open', icon: ExternalLink, onSelect: () => setOpenName(i.name) },
                        { label: 'Reprocess', icon: RefreshCw, disabled: adding, onSelect: () => void onReprocess(i.name) },
                        { label: 'Remove', icon: Trash2, destructive: true, onSelect: () => setRemoveTarget(i.name) },
                      ]}
                    />
                  }
                />
              );
            })}
      </ResourceList>
      <DocumentDetailSheet input={inputs.find((i) => i.name === openName) ?? null} onOpenChange={(o) => !o && setOpenName(null)} />
      <ConfirmActionDialog
        open={removeTarget !== null}
        onOpenChange={(o) => !o && setRemoveTarget(null)}
        title="Remove this document?"
        description="It is removed from this source and agents can no longer use it. This cannot be undone."
        confirmLabel="Remove"
        destructive
        onConfirm={async () => {
          const target = removeTarget;
          setRemoveTarget(null);
          if (target) await onRemove(target);
        }}
      />
    </>
  );
}
