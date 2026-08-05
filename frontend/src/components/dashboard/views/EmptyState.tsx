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
  title = 'Nothing here yet',
  description = 'Items you create will show up here.',
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center p-10',
        className,
      )}
    >
      {Icon && <Icon className="h-[22px] w-[22px] text-steel-soft" />}
      {title && (
        <h3 className="text-[15px] font-medium text-ink mt-3">{title}</h3>
      )}
      {description && (
        <p className="font-body text-[13px] text-steel mt-1">{description}</p>
      )}
      {action && (
        <Button
          variant="outline"
          size="sm"
          className="mt-5"
          onClick={action.onClick}
        >
          {action.label}
        </Button>
      )}
    </div>
  );
}
