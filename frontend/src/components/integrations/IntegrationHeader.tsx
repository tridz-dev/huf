import { Save, Trash2, Link2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface IntegrationHeaderProps {
  title: string;
  service: string;
  isActive: boolean;
  isDefault: boolean;
  isNew: boolean;
  showSaveButton: boolean;
  saving: boolean;
  deleting?: boolean;
  onSave: () => void;
  onDelete?: () => void;
}

export function IntegrationHeader({
  title,
  service,
  isActive,
  isDefault,
  isNew,
  showSaveButton,
  saving,
  deleting = false,
  onSave,
  onDelete,
}: IntegrationHeaderProps) {
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div className="flex-1 space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl font-bold capitalize">
            {isNew ? `New ${service.replace(/_/g, ' ')} Integration` : title}
          </h1>
          {!isNew && (
            <>
              <Badge variant={isActive ? 'default' : 'secondary'}>
                {isActive ? 'Active' : 'Inactive'}
              </Badge>
              {isDefault && <Badge variant="outline">Default</Badge>}
            </>
          )}
          <Badge variant="outline">
            <Link2 className="w-3 h-3 mr-1" />
            {service.replace(/_/g, ' ')}
          </Badge>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {!isNew && onDelete && (
          <Button
            variant="outline"
            size="sm"
            onClick={onDelete}
            disabled={saving || deleting}
            type="button"
            className="text-destructive hover:text-destructive"
          >
            <Trash2 className={cn('w-4 h-4 mr-2', deleting && 'animate-pulse')} />
            {deleting ? 'Deleting...' : 'Delete'}
          </Button>
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
