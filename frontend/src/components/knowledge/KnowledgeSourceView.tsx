import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import type { UseFormReturn } from 'react-hook-form';
import type { AIProvider } from '@/types/agent.types';
import type { KnowledgeInputDoc, KnowledgeSourceDoc } from '@/types/knowledge.types';
import { deleteKnowledgeSource } from '@/services/knowledgeApi';
import { getAgentsForSource } from '@/services/knowledge/usageApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { AddContentDialog } from './import/AddContentDialog';
import { ConfirmActionDialog } from './import/ConfirmActionDialog';
import { IngestionProblemsSheet } from './import/IngestionProblemsSheet';
import type { SourceFilter } from './import/docFilter';
import { SourceAskResults, useSourceAsk } from './source/SourceAskResults';
import { SourceDocuments } from './source/SourceDocuments';
import { SourceFrame } from './source/SourceFrame';
import { SourceHistorySheet } from './source/SourceHistorySheet';
import { SourceImportProgress } from './source/SourceImportProgress';
import { SourceSettingsSheet } from './source/SourceSettingsSheet';
import { SourceToolbar } from './source/SourceToolbar';
import { useKnowledgeOverview } from './useKnowledgeOverview';
import type { KnowledgeSourceFormValues } from './types';

interface KnowledgeSourceViewProps {
  form: UseFormReturn<KnowledgeSourceFormValues>;
  source: KnowledgeSourceDoc;
  providers: AIProvider[];
  inputs: KnowledgeInputDoc[];
  inputsLoading: boolean;
  dirty: boolean;
  saving: boolean;
  rebuilding: boolean;
  fromAgent?: string;
  addOpen: boolean;
  onAddOpenChange: (open: boolean) => void;
  onSubmit: () => void;
  onCancel?: () => void;
  onRebuildIndex: () => void;
  onToggleDisabled: () => void;
  /** Refetch source + inputs (never saves the source). */
  onChanged: () => void;
  onReprocessInput: (name: string) => Promise<void> | void;
  onDeleteInput: (name: string) => Promise<void> | void;
}

/** Existing-source page: one tabless resource page composed from the DS patterns. */
export function KnowledgeSourceView(props: KnowledgeSourceViewProps) {
  const { form, source, inputs } = props;
  const navigate = useNavigate();
  const overview = useKnowledgeOverview(source.name, source, inputs);
  const { counts } = overview;
  const ask = useSourceAsk(source);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<SourceFilter>('all');
  const [shown, setShown] = useState<string | null>(null);
  const [problemsFor, setProblemsFor] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ label: string; done: number; total: number } | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [dropped, setDropped] = useState<File[]>([]);
  const [addTab, setAddTab] = useState<'upload' | 'storage'>('upload');
  const [agentCount, setAgentCount] = useState(0);
  const ingestion = shown ?? overview.active;
  const hasDocs = counts.total > 0 || !!ingestion;
  const searching = query.trim() !== '' && (ask.asked !== '' || ask.searching);

  useEffect(() => {
    let alive = true;
    getAgentsForSource(source.name)
      .then((a) => alive && setAgentCount(a.length))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [source.name]);

  const submitAsk = () => void ask.run(query);
  const changeQuery = (v: string) => {
    setQuery(v);
    if (!v.trim()) ask.clear();
  };
  const openAdd = (tab: 'upload' | 'storage') => {
    setAddTab(tab);
    props.onAddOpenChange(true);
  };
  const confirmDelete = async () => {
    setDeleting(true);
    try {
      await deleteKnowledgeSource(source.name);
      toast.success('Knowledge source deleted');
      navigate('/knowledge', { replace: true });
    } catch (e) {
      toast.error(getFrappeErrorMessage(e) || 'Could not delete this knowledge source');
      setDeleting(false);
    }
  };

  return (
    <>
      <SourceFrame
        form={form}
        knowledgeSource={source.name}
        sourceStatus={source.status}
        disabled={source.disabled === 1}
        rebuilding={props.rebuilding}
        counts={counts}
        health={overview.health}
        importing={progress}
        agentCount={agentCount}
        onAddContent={() => openAdd('upload')}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenHistory={() => setHistoryOpen(true)}
        onRebuildIndex={props.onRebuildIndex}
        onToggleDisabled={props.onToggleDisabled}
        onReview={() => {
          setQuery('');
          ask.clear();
          setFilter('attention');
        }}
      >
        <div className="space-y-4" data-testid="source-page">
          <SourceToolbar
            query={query}
            onQueryChange={changeQuery}
            onSubmit={submitAsk}
            filter={filter}
            onFilterChange={setFilter}
            counts={counts}
            hasDocs={hasDocs}
          />
          {searching ? (
            <SourceAskResults
              asked={ask.asked}
              searching={ask.searching}
              results={ask.results}
              error={ask.error}
              blocked={ask.blocked}
              onClear={() => changeQuery('')}
              onOpenDocument={() => changeQuery('')}
            />
          ) : (
            <SourceDocuments
              knowledgeSource={source.name}
              inputs={inputs}
              loading={props.inputsLoading}
              counts={counts}
              filter={filter}
              onFilterChange={setFilter}
              slot={
                ingestion ? (
                  <SourceImportProgress
                    key={ingestion}
                    ingestion={ingestion}
                    onProgress={setProgress}
                    onViewDetails={setProblemsFor}
                    onFinished={() => {
                      setShown(null);
                      setProgress(null);
                      overview.refresh();
                      props.onChanged();
                    }}
                  />
                ) : undefined
              }
              onAddContent={openAdd}
              onFiles={(files) => {
                setDropped(files);
                openAdd('upload');
              }}
              onRetried={(ing) => {
                if (ing) setShown(ing);
                overview.refresh();
                props.onChanged();
              }}
              onReprocess={props.onReprocessInput}
              onRemove={props.onDeleteInput}
            />
          )}
        </div>
      </SourceFrame>
      <IngestionProblemsSheet
        ingestion={problemsFor}
        onOpenChange={(o) => !o && setProblemsFor(null)}
        onRetried={() => {
          setShown(problemsFor);
          overview.refresh();
        }}
      />
      <AddContentDialog
        open={props.addOpen}
        onOpenChange={(o) => {
          if (!o) setDropped([]);
          props.onAddOpenChange(o);
        }}
        knowledgeSource={source.name}
        sourceLabel={source.source_name}
        initialTab={addTab}
        initialFiles={dropped}
        onInputAdded={() => {
          overview.refresh();
          props.onChanged();
        }}
        onStarted={(name) => {
          setDropped([]);
          setShown(name);
          overview.refresh();
          props.onChanged();
        }}
      />
      <SourceSettingsSheet
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        form={form}
        source={source}
        providers={props.providers}
        documentCount={counts.total}
        dirty={props.dirty}
        saving={props.saving}
        onSave={props.onSubmit}
        onDelete={() => setDeleteOpen(true)}
      />
      <SourceHistorySheet
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        knowledgeSource={source.name}
        refreshKey={overview.bump}
      />
      <ConfirmActionDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete this knowledge source?"
        description="This removes the source and all of its documents. Agents using it will lose access. This cannot be undone."
        confirmLabel="Delete source"
        destructive
        busy={deleting}
        onConfirm={confirmDelete}
      />
    </>
  );
}
