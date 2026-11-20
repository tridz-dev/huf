import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { MoreHorizontal, PauseCircle, PlayCircle, Plus, Save, RotateCcw, Search, Trash2 } from 'lucide-react';
import { UseFormReturn } from 'react-hook-form';
import { deleteKnowledgeSource } from '@/services/knowledgeApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { InlineEditName } from '@/components/common/InlineEditName';
import { ConfirmActionDialog } from './import/ConfirmActionDialog';
import { AgentUsageLink } from './AgentUsageLink';
import { HealthBadge } from './import/DocumentsSummary';
import type { Health } from './import/ingestionLabels';
import type { KnowledgeSourceFormValues } from './types';

interface KnowledgeSourceHeaderProps {
  form: UseFormReturn<KnowledgeSourceFormValues>;
  isNew: boolean;
  health?: Health;
  disabled: boolean;
  saving: boolean;
  rebuilding: boolean;
  sourceStatus?: string;
  fromAgent?: string;
  onSave: () => void;
  onCancel?: () => void;
  onRebuildIndex: () => void;
  onAddContent: () => void;
  onTest: () => void;
  onToggleDisabled: () => void;
}

export function KnowledgeSourceHeader({
  form,
  isNew,
  health,
  disabled,
  saving,
  rebuilding,
  sourceStatus,
  fromAgent,
  onSave,
  onCancel,
  onRebuildIndex,
  onAddContent,
  onTest,
  onToggleDisabled,
}: KnowledgeSourceHeaderProps) {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [rebuildOpen, setRebuildOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const indexing = rebuilding || sourceStatus === 'Indexing' || sourceStatus === 'Rebuilding';

  const confirmDelete = async () => {
    if (!id) return;
    setDeleting(true);
    try {
      await deleteKnowledgeSource(id);
      toast.success('Knowledge source deleted');
      navigate('/knowledge', { replace: true });
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Could not delete this knowledge source');
      setDeleting(false);
    }
  };

  const name = form.watch('source_name');
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div className="flex flex-1 flex-wrap items-center gap-3">
        {isNew ? (
          <Input
            value={name}
            onChange={(e) => form.setValue('source_name', e.target.value, { shouldDirty: true })}
            className="h-auto max-w-md border-0 px-0 text-2xl font-bold focus-visible:ring-0"
            placeholder="e.g. Product documentation"
          />
        ) : (
          <InlineEditName
            value={name}
            onChange={(value) => form.setValue('source_name', value, { shouldDirty: true })}
            placeholder="e.g. Product documentation"
          />
        )}
        {health && <HealthBadge health={health} />}
        {!isNew && id && <AgentUsageLink knowledgeSource={id} />}
      </div>
      <div className="flex items-center gap-2">
        {fromAgent && onCancel && (
          <Button size="sm" variant="outline" onClick={onCancel} type="button" disabled={saving}>
            Cancel
          </Button>
        )}
        {isNew ? (
          <Button size="sm" onClick={onSave} disabled={saving}>
            <Save className="mr-2 h-4 w-4" />
            {saving ? 'Creating...' : 'Create'}
          </Button>
        ) : (
          <>
            <Button type="button" size="sm" onClick={onAddContent} data-testid="add-content">
              <Plus className="mr-2 h-4 w-4" />
              Add content
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={onTest}>
              <Search className="mr-2 h-4 w-4" />
              Test
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button type="button" variant="outline" size="icon-sm" aria-label="More actions">
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={onToggleDisabled}>
                  {disabled ? <PlayCircle className="mr-2 h-4 w-4" /> : <PauseCircle className="mr-2 h-4 w-4" />}
                  {disabled ? 'Turn on' : 'Turn off'}
                </DropdownMenuItem>
                <DropdownMenuItem disabled={indexing} onSelect={() => setRebuildOpen(true)}>
                  <RotateCcw className="mr-2 h-4 w-4" />
                  Rebuild search index
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem className="text-destructive" onSelect={() => setDeleteOpen(true)} data-testid="delete-source-menu">
                  <Trash2 className="mr-2 h-4 w-4" />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        )}
      </div>
      <ConfirmActionDialog
        open={rebuildOpen}
        onOpenChange={setRebuildOpen}
        title="Rebuild the search index?"
        description="We will read all documents again. This can take a while, and search may be slower until it finishes."
        confirmLabel="Rebuild"
        onConfirm={() => {
          setRebuildOpen(false);
          onRebuildIndex();
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
    </div>
  );
}
