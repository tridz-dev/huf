import { LucideIcon, PackageOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface EmptyStateProps {
  icon?: LucideIcon;
  title?: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export function EmptyState({
  icon: Icon = PackageOpen,
  title = 'No items',
  description = 'There are no items to display.',
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center border border-line bg-panel p-10',
        className,
      )}
    >
      {Icon && (
        <div className="flex h-12 w-12 items-center justify-center border border-line bg-paper-deep mb-5">
          <Icon className="h-6 w-6 text-steel" />
        </div>
      )}
      {title && (
        <h3 className="font-display font-bold text-[18px] uppercase tracking-[.02em] text-ink">
          {title}
        </h3>
      )}
      {description && (
        <p className="font-body text-[13px] text-steel mt-1">{description}</p>
      )}
      {action && (
        <Button
          variant="outline"
          size="sm"
          className="mt-5 border-line text-ink hover:bg-paper-deep rounded"
          onClick={action.onClick}
        >
          {action.label}
        </Button>
      )}
    </div>
  );
}
