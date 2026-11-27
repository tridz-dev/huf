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
import { Checkbox } from '@/components/ui/checkbox';
import { useResourceAccess } from '@/hooks/permissions/useResourceAccess';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { reprocessInput, retryIngestion, type ImportOptions } from '@/services/knowledgeApi';
import { formatTimeAgo } from '@/utils/time';
import type { KnowledgeInputDoc } from '@/types/knowledge.types';
import { BulkDeleteInputs } from './BulkDeleteInputs';
import { DocumentDetailSheet } from '../DocumentDetailSheet';
import { inputOrigin, inputTitle } from '../inputDisplay';
import { ConfirmActionDialog } from '../import/ConfirmActionDialog';
import { DOC_FILTER_STATUS, type SourceFilter } from '../import/docFilter';
import { itemReason, itemStatusLabel, type InputCounts } from '../import/ingestionLabels';

const STEPS = [
  { title: 'Add documents', description: 'Files, web pages or storage' },
  { title: 'Try a question', description: 'See what your agents would find' },
  { title: 'Connect to an agent', description: 'Let an agent use it' },
];

/** Accept list and plain-words hint from the backend's import options (no hardcoded types). */
export function dropZoneCopy(options?: ImportOptions | null): { accept?: string; hint?: string } {
  const exts = (options?.allowed_extensions ?? []).map((e) => e.replace(/^\./, '').toLowerCase()).filter(Boolean);
  if (exts.length === 0) return {};
  const size = options?.max_file_mb ? ` Up to ${options.max_file_mb} MB each.` : '';
  return { accept: exts.map((e) => `.${e}`).join(','), hint: `${exts.map((e) => e.toUpperCase()).join(', ')}.${size}` };
}

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
  importOptions?: ImportOptions | null;
  onRetried: (ingestion?: string) => void;
  /** After a bulk delete: refresh the inputs, counts and source stats (once). */
  onBulkDeleted?: () => void;
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
  knowledgeSource,
  inputs,
  loading,
  counts,
  filter,
  onFilterChange,
  slot,
  onAddContent,
  onFiles,
  importOptions,
  onRetried,
  onBulkDeleted,
  onReprocess,
  onRemove,
}: SourceDocumentsProps) {
  const [retrying, setRetrying] = useState(false);
  const [openName, setOpenName] = useState<string | null>(null);
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const selectable = useResourceAccess('knowledge').canDelete && !!onBulkDeleted;

  const retryAll = async () => {
    setRetrying(true);
    try {
      const failed = inputs.filter((i) => i.status === 'Error');
      const ingestions = [...new Set(failed.map((i) => i.ingestion).filter((x): x is string => !!x))];
      const orphans = failed.filter((i) => !i.ingestion);
      const results = await Promise.allSettled([
        ...ingestions.map((ing) => retryIngestion(ing, true)),
        ...orphans.map((i) => reprocessInput(i.name)),
      ]);
      const okCount = results.filter((r) => r.status === 'fulfilled').length;
      const bad = results.length - okCount;
      const parts = [
        ingestions.length ? `${ingestions.length} ${ingestions.length === 1 ? 'import' : 'imports'}` : '',
        orphans.length ? `${orphans.length} ${orphans.length === 1 ? 'document' : 'documents'}` : '',
      ].filter(Boolean);
      if (bad === 0) toast.success(`Retrying ${failed.length} failed ${failed.length === 1 ? 'document' : 'documents'} (${parts.join(', ')}).`);
      else if (okCount > 0) toast.warning(`Retried ${okCount} of ${results.length} (${parts.join(', ')}); ${bad} could not be retried.`);
      else toast.error('Could not retry the failed documents');
      if (okCount > 0) onRetried(ingestions[0]);
    } finally {
      setRetrying(false);
    }
  };

  const [reprocessing, setReprocessing] = useState<string | null>(null);
  const retryOne = async (name: string) => {
    setReprocessing(name);
    try {
      await onReprocess(name);
    } catch (e) {
      toast.error(getFrappeErrorMessage(e) || 'Could not retry');
    } finally {
      setReprocessing(null);
    }
  };

  if (counts.total === 0 && !loading && !slot) {
    return (
      <div className="space-y-6" data-testid="documents-empty">
        <StepHint current={0} steps={STEPS} />
        <DropZone
          title="Drop files here to add them"
          {...dropZoneCopy(importOptions)}
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
  const selectedNames = rows.filter((i) => selected.has(i.name)).map((i) => i.name);
  const allOn = rows.length > 0 && selectedNames.length === rows.length;
  const toggle = (name: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(name);
      else next.delete(name);
      return next;
    });

  return (
    <>
      <ResourceList label="Documents">
        {slot}
        {selectable && rows.length > 0 && (
          <ResourceListSlot>
            <div className="flex items-center gap-3 border-b border-line px-4 py-2 text-meta text-steel">
              <Checkbox
                aria-label="Select all documents"
                checked={allOn ? true : selectedNames.length > 0 ? 'indeterminate' : false}
                onCheckedChange={(v) => setSelected(v === true ? new Set(rows.map((i) => i.name)) : new Set())}
              />
              <span>{selectedNames.length > 0 ? `${selectedNames.length.toLocaleString()} of ${rows.length.toLocaleString()} selected` : 'Select all'}</span>
            </div>
          </ResourceListSlot>
        )}
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
                  selected={selected.has(i.name)}
                  onSelectedChange={selectable ? (on) => toggle(i.name, on) : undefined}
                  selectLabel={`Select ${title}`}
                  reason={
                    i.status === 'Error' ? (
                      <>
                        {itemReason(i)}{' '}
                        <Button type="button" variant="link" size="sm" disabled={reprocessing === i.name} onClick={() => void retryOne(i.name)}>
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
                        { label: 'Reprocess', icon: RefreshCw, disabled: adding || reprocessing === i.name, onSelect: () => void retryOne(i.name) },
                        { label: 'Remove', icon: Trash2, destructive: true, onSelect: () => setRemoveTarget(i.name) },
                      ]}
                    />
                  }
                />
              );
            })}
      </ResourceList>
      {selectable && (
        <BulkDeleteInputs
          knowledgeSource={knowledgeSource}
          names={selectedNames}
          onClear={() => setSelected(new Set())}
          onDeleted={(deleted) => {
            setSelected(new Set());
            if (deleted.length > 0) onBulkDeleted?.();
          }}
        />
      )}
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
