import { Save, Trash2, Link2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { InlineEditName } from '@/components/common/InlineEditName';

interface IntegrationServiceHeaderProps {
  title: string;
  isBuiltin: boolean;
  isNew: boolean;
  showSaveButton: boolean;
  saving: boolean;
  deleting?: boolean;
  canDelete: boolean;
  onSave: () => void;
  onDelete?: () => void;
  onTitleChange: (value: string) => void;
}

export function IntegrationServiceHeader({
  title,
  isBuiltin,
  isNew,
  showSaveButton,
  saving,
  deleting = false,
  canDelete,
  onSave,
  onDelete,
  onTitleChange,
}: IntegrationServiceHeaderProps) {
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div className="flex-1 space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          {isNew ? (
            <h1 className="font-display text-title text-ink">
              New Integration Service
            </h1>
          ) : (
            <InlineEditName
              value={title}
              onChange={onTitleChange}
              placeholder="e.g. WhatsApp integration"
            />
          )}
          {!isNew && isBuiltin && <Badge variant="outline">Built-in</Badge>}
          <Badge variant="outline">
            <Link2 className="w-3 h-3 mr-1" />
            Service catalog
          </Badge>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {!isNew && onDelete && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={onDelete}
                    disabled={saving || deleting || !canDelete}
                    type="button"
                    className="text-destructive hover:text-destructive"
                  >
                    <Trash2 className={cn('w-4 h-4 mr-2', deleting && 'animate-pulse')} />
                    {deleting ? 'Deleting...' : 'Delete'}
                  </Button>
                </span>
              </TooltipTrigger>
              {!canDelete && (
                <TooltipContent>Built-in services cannot be deleted</TooltipContent>
              )}
            </Tooltip>
          </TooltipProvider>
        )}
        {showSaveButton && (
          <Button size="sm" onClick={onSave} disabled={saving || deleting}>
            <Save className="w-4 h-4 mr-2" />
            {saving ? (isNew ? 'Creating...' : 'Saving...') : (isNew ? 'Create' : 'Save')}
          </Button>
        )}
      </div>
    </div>
  );
}
