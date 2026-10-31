import type { ReactNode } from 'react';
import { Save, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface IntegrationHeaderProps {
  /** Friendly name: the user's label, or the service and account. Never the auto id. */
  title: string;
  /** One line under the title: the service, and whether this is the default one. */
  subtitle?: string;
  isNew: boolean;
  showSaveButton: boolean;
  saving: boolean;
  deleting?: boolean;
  onSave: () => void;
  onDelete?: () => void;
  /** The single status line (pill, sentence, next-step button). */
  status?: ReactNode;
  /** Buttons that come before Delete and Save (Test connection, Use in agent). */
  children?: ReactNode;
}

export function IntegrationHeader({
  title,
  subtitle,
  isNew,
  showSaveButton,
  saving,
  deleting = false,
  onSave,
  onDelete,
  status,
  children,
}: IntegrationHeaderProps) {
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between" data-testid="integration-header">
      <div className="min-w-0 flex-1 space-y-1.5">
        <h1 className="break-words font-display text-title text-ink" data-testid="integration-title">
          {title}
        </h1>
        {subtitle && <p className="text-sm text-steel">{subtitle}</p>}
        {status}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {children}
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
          <Button size="sm" onClick={onSave} disabled={saving || deleting} data-testid="integration-save">
            <Save className="w-4 h-4 mr-2" />
            {saving ? (isNew ? 'Creating...' : 'Saving...') : isNew ? 'Create' : 'Save'}
          </Button>
        )}
      </div>
    </div>
  );
}
