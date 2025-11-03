import { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface PageSectionProps {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function PageSection({
  title,
  description,
  actions,
  children,
  className,
}: PageSectionProps) {
  return (
    <div className={cn('space-y-4', className)}>
      {(title || description || actions) && (
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            {title && (
              <h2 className="text-lg font-semibold">{title}</h2>
            )}
            {description && (
              <p className="text-sm text-muted-foreground">{description}</p>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div>{children}</div>
    </div>
  );
}
