import { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface PageLayoutProps {
  subtitle?: string;
  filters?: ReactNode;
  toolbar?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function PageLayout({
  subtitle,
  filters,
  toolbar,
  children,
  className,
}: PageLayoutProps) {
  return (
    <div className="h-full overflow-auto">
      <div className={cn('p-6 space-y-6', className)}>
        {(subtitle || toolbar) && (
          <div className="flex items-center justify-between gap-4">
            {subtitle && (
              <p className="text-muted-foreground">{subtitle}</p>
            )}
            {toolbar && <div className="flex items-center gap-2">{toolbar}</div>}
          </div>
        )}

        {filters && <div>{filters}</div>}

        <div>{children}</div>
      </div>
    </div>
  );
}
