import { Save, MoreVertical, RefreshCw, Database, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { UseFormReturn } from 'react-hook-form';
import type { KnowledgeSourceFormValues } from './types';

interface KnowledgeSourceHeaderProps {
  form: UseFormReturn<KnowledgeSourceFormValues>;
  watchDisabled: boolean;
  isNew: boolean;
  showSaveButton: boolean;
  saving: boolean;
  rebuilding: boolean;
  refreshing: boolean;
  sourceStatus?: string;
  onSave: () => void;
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
  onSave,
  onRebuildIndex,
  onRefresh,
  onOpenInputs,
}: KnowledgeSourceHeaderProps) {
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div className="flex-1 space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          <Input
            value={form.watch('source_name')}
            onChange={(e) => form.setValue('source_name', e.target.value, { shouldDirty: true })}
            className="text-2xl font-bold h-auto border-0 px-0 focus-visible:ring-0 max-w-md"
            placeholder="Source Name"
            disabled={!isNew}
          />
          <Badge variant={watchDisabled ? 'secondary' : 'default'}>
            {watchDisabled ? 'Disabled' : 'Active'}
          </Badge>
          {sourceStatus && (
            <Badge variant="outline">{sourceStatus}</Badge>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
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
            Knowledge Inputs
          </Button>
        )}
        {!isNew && (
          <Button
            variant="outline"
            size="sm"
            onClick={onRebuildIndex}
            type="button"
            disabled={rebuilding || sourceStatus === 'Indexing' || sourceStatus === 'Rebuilding'}
          >
            <RotateCcw className={`w-4 h-4 mr-2 ${rebuilding || sourceStatus === 'Indexing' || sourceStatus === 'Rebuilding' ? 'animate-spin' : ''}`} />
            {rebuilding || sourceStatus === 'Rebuilding' ? 'Rebuilding...' : sourceStatus === 'Indexing' ? 'Indexing...' : 'Rebuild Index'}
          </Button>
        )}
        {showSaveButton && (
          <Button size="sm" onClick={onSave} disabled={saving}>
            <Save className="w-4 h-4 mr-2" />
            {saving ? (isNew ? 'Creating...' : 'Saving...') : (isNew ? 'Create' : 'Save')}
          </Button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              <MoreVertical className="w-4 h-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <div className="px-2 py-1.5">
              <div className="flex items-center justify-between">
                <span className="text-sm">Disable</span>
                <Switch
                  checked={watchDisabled}
                  onCheckedChange={(checked) => form.setValue('disabled', checked)}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
            </div>
            {!isNew && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onRefresh}>
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Refresh
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
