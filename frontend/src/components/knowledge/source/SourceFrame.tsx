import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { History, PauseCircle, PlayCircle, Plug, Plus, RotateCcw, Settings, Trash2 } from 'lucide-react';
import type { UseFormReturn } from 'react-hook-form';
import { PageFrame } from '@/layouts/PageFrame';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { InlineEditName } from '@/components/common/InlineEditName';
import { OverflowMenu, StatusSentence, type Tone } from '@/components/patterns';
import { deleteKnowledgeSource } from '@/services/knowledgeApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { ConfirmActionDialog } from '../import/ConfirmActionDialog';
import type { Health, InputCounts } from '../import/ingestionLabels';
import type { KnowledgeSourceFormValues } from '../types';

export interface SourceFrameProps {
  form: UseFormReturn<KnowledgeSourceFormValues>;
  knowledgeSource: string;
  sourceStatus?: string;
  disabled: boolean;
  rebuilding: boolean;
  counts: InputCounts;
  health: Health;
  importing: null | { label: string; done: number; total: number };
  /** Agents that use this source (names). */
  agents?: string[];
  onConnectAgent: () => void;
  /** Increment to open the delete confirm (Settings → Delete reuses it). */
  deleteRequest?: number;
  onAddContent: () => void;
  onOpenSettings: () => void;
  onOpenHistory: () => void;
  onRebuildIndex: () => void;
  onToggleDisabled: () => void;
  onReview: () => void;
  children: ReactNode;
}

const n = (v: number) => v.toLocaleString();

function UsedBy({ agents, onConnect }: { agents: string[]; onConnect: () => void }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" data-testid="used-by" className="rounded-sm underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          used by {n(agents.length)} {agents.length === 1 ? 'agent' : 'agents'}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-2">
        <ul className="space-y-0.5">
          {agents.map((a) => (
            <li key={a}>
              <Link to={`/agents/${encodeURIComponent(a)}`} className="block truncate rounded px-2 py-1.5 text-sm hover:bg-muted">
                {a}
              </Link>
            </li>
          ))}
        </ul>
        <button type="button" onClick={onConnect} className="mt-1 w-full rounded px-2 py-1.5 text-left text-sm text-signal-ink hover:bg-muted">
          Connect another agent
        </button>
      </PopoverContent>
    </Popover>
  );
}

function StatusLine({
  counts,
  disabled,
  importing,
  agents,
  onReview,
  onConnectAgent,
}: Pick<SourceFrameProps, 'counts' | 'disabled' | 'importing' | 'onReview' | 'onConnectAgent'> & { agents: string[] }) {
  if (counts.failed > 0) {
    return (
      <StatusSentence tone="attention" action={{ label: 'Review', onClick: onReview }}>
        <strong className="font-semibold text-ink">
          {n(counts.failed)} {counts.failed === 1 ? 'document needs' : 'documents need'} attention
        </strong>
      </StatusSentence>
    );
  }
  if (importing) {
    const found = importing.total > 0 ? `${n(importing.done)} of ${n(importing.total)}` : `${n(importing.done)} found so far`;
    return <StatusSentence tone="live" live parts={[importing.label || 'Importing', found]} />;
  }
  if (disabled) return <StatusSentence tone="off" parts={['Turned off']} />;
  if (counts.total > 0) {
    return (
      <StatusSentence
        tone={'ready' as Tone}
        parts={[
          'Ready',
          `${n(counts.total)} ${counts.total === 1 ? 'document' : 'documents'}`,
          agents.length > 0 && <UsedBy key="used" agents={agents} onConnect={onConnectAgent} />,
        ]}
        action={agents.length === 0 ? { label: 'Connect to an agent', onClick: onConnectAgent } : undefined}
      />
    );
  }
  return <StatusSentence tone="off" parts={['No documents yet']} />;
}

export function SourceFrame(props: SourceFrameProps) {
  const { form, knowledgeSource, sourceStatus, disabled, rebuilding, counts, importing, children } = props;
  const agents = props.agents ?? [];
  const navigate = useNavigate();
  const [rebuildOpen, setRebuildOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const indexing = rebuilding || sourceStatus === 'Indexing' || sourceStatus === 'Rebuilding';
  const name = form.watch('source_name');
  const lastDelete = useRef(props.deleteRequest ?? 0);
  useEffect(() => {
    if ((props.deleteRequest ?? 0) !== lastDelete.current) {
      lastDelete.current = props.deleteRequest ?? 0;
      setDeleteOpen(true);
    }
  }, [props.deleteRequest]);

  const confirmDelete = async () => {
    setDeleting(true);
    try {
      await deleteKnowledgeSource(knowledgeSource);
      toast.success('Knowledge source deleted');
      navigate('/knowledge', { replace: true });
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Could not delete this knowledge source');
      setDeleting(false);
    }
  };

  return (
    <>
      <PageFrame
        title={
          <InlineEditName
            value={name}
            onChange={(value) => form.setValue('source_name', value, { shouldDirty: true })}
            placeholder="e.g. Product documentation"
          />
        }
        meta={
          <StatusLine counts={counts} disabled={disabled} importing={importing} agents={agents} onReview={props.onReview} onConnectAgent={props.onConnectAgent} />
        }
        actions={
          <>
            <Button type="button" size="sm" onClick={props.onAddContent} data-testid="add-content">
              <Plus className="mr-2 h-4 w-4" />
              Add content
            </Button>
            <OverflowMenu
              items={[
                { label: 'Settings', icon: Settings, onSelect: props.onOpenSettings },
                { label: 'History', icon: History, onSelect: props.onOpenHistory },
                { label: 'Connect to an agent', icon: Plug, onSelect: props.onConnectAgent },
                { label: 'Rebuild search index', icon: RotateCcw, disabled: indexing, onSelect: () => setRebuildOpen(true) },
                {
                  label: disabled ? 'Turn on' : 'Turn off',
                  icon: disabled ? PlayCircle : PauseCircle,
                  separated: true,
                  onSelect: props.onToggleDisabled,
                },
                { label: 'Delete', icon: Trash2, destructive: true, onSelect: () => setDeleteOpen(true) },
              ]}
            />
          </>
        }
      >
        {children}
      </PageFrame>
      <ConfirmActionDialog
        open={rebuildOpen}
        onOpenChange={setRebuildOpen}
        title="Rebuild the search index?"
        description="We will read all documents again. This can take a while, and search may be slower until it finishes."
        confirmLabel="Rebuild"
        onConfirm={() => {
          setRebuildOpen(false);
          props.onRebuildIndex();
        }}
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
