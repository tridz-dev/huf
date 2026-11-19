import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Save, RefreshCw, Database, RotateCcw, Trash2 } from 'lucide-react';
import { deleteKnowledgeSource } from '@/services/knowledgeApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { ConfirmActionDialog } from './import/ConfirmActionDialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { UseFormReturn } from 'react-hook-form';
import type { KnowledgeSourceFormValues } from './types';
import { InlineEditName } from '@/components/common/InlineEditName';

interface KnowledgeSourceHeaderProps {
  form: UseFormReturn<KnowledgeSourceFormValues>;
  watchDisabled: boolean;
  isNew: boolean;
  showSaveButton: boolean;
  saving: boolean;
  rebuilding: boolean;
  refreshing: boolean;
  sourceStatus?: string;
  fromAgent?: string;
  onSave: () => void;
  onCancel?: () => void;
  onRebuildIndex: () => void;
  onRefresh: () => void;
  onOpenInputs: () => void;
}

export function KnowledgeSourceHeader({
  form,
  watchDisabled,
  isNew,
  showSaveButton,
  saving,
  rebuilding,
  refreshing,
  sourceStatus,
  fromAgent,
  onSave,
  onCancel,
  onRebuildIndex,
  onRefresh,
  onOpenInputs,
}: KnowledgeSourceHeaderProps) {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [rebuildOpen, setRebuildOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

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

  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div className="flex-1 space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          {isNew ? (
            <Input
              value={form.watch('source_name')}
              onChange={(e) => form.setValue('source_name', e.target.value, { shouldDirty: true })}
              className="text-2xl font-bold h-auto border-0 px-0 focus-visible:ring-0 max-w-md"
              placeholder="e.g. Product documentation"
            />
          ) : (
            <InlineEditName
              value={form.watch('source_name')}
              onChange={(value) => form.setValue('source_name', value, { shouldDirty: true })}
              placeholder="e.g. Product documentation"
            />
          )}
          <Badge variant={watchDisabled ? 'secondary' : 'default'}>
            {watchDisabled ? 'Disabled' : 'Active'}
          </Badge>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-2 mr-2">
          <Label htmlFor="knowledge-source-disabled" className="text-sm font-normal">
            Disable
          </Label>
          <Switch
            id="knowledge-source-disabled"
            checked={watchDisabled}
            onCheckedChange={(checked) => form.setValue('disabled', checked)}
          />
        </div>
        {fromAgent && onCancel && (
          <Button size="sm" variant="outline" onClick={onCancel} type="button" disabled={saving}>
            Cancel
          </Button>
        )}
        {!isNew && (
          <Button
            variant="outline"
            size="icon-sm"
            onClick={onRefresh}
            type="button"
            disabled={refreshing}
            title="Refresh status"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          </Button>
        )}
        {!isNew && (
          <Button
            variant="outline"
            size="sm"
            onClick={onOpenInputs}
            type="button"
          >
            <Database className="w-4 h-4 mr-2" />
            Links and text
          </Button>
        )}
        {!isNew && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setRebuildOpen(true)}
            type="button"
            disabled={rebuilding || sourceStatus === 'Indexing' || sourceStatus === 'Rebuilding'}
          >
            <RotateCcw className={`w-4 h-4 mr-2 ${rebuilding || sourceStatus === 'Indexing' || sourceStatus === 'Rebuilding' ? 'animate-spin' : ''}`} />
            {rebuilding || sourceStatus === 'Rebuilding' ? 'Rebuilding...' : sourceStatus === 'Indexing' ? 'Indexing...' : 'Rebuild search index'}
          </Button>
        )}
        {!isNew && (
          <Button
            variant="outline"
            size="icon-sm"
            type="button"
            onClick={() => setDeleteOpen(true)}
            title="Delete knowledge source"
            aria-label="Delete knowledge source"
            data-testid="delete-source"
            className="text-destructive hover:text-destructive"
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        )}
        {showSaveButton && (
          <Button size="sm" onClick={onSave} disabled={saving}>
            <Save className="w-4 h-4 mr-2" />
            {saving ? (isNew ? 'Creating...' : 'Saving...') : (isNew ? 'Create' : 'Save')}
          </Button>
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
