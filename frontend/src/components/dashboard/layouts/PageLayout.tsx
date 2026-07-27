import { ReactNode, RefObject } from 'react';
import { cn } from '@/lib/utils';

interface PageLayoutProps {
  title?: ReactNode;
  badge?: ReactNode;
  subtitle?: string;
  filters?: ReactNode;
  toolbar?: ReactNode;
  children: ReactNode;
  className?: string;
  scrollRef?: RefObject<HTMLDivElement>;
}

export function PageLayout({
  title,
  badge,
  subtitle,
  filters,
  toolbar,
  children,
  className,
  scrollRef,
}: PageLayoutProps) {
  return (
    <div ref={scrollRef} className="h-full overflow-auto">
      <div className={cn('p-6 space-y-6', className)}>
        {(title || subtitle || toolbar) && (
          <div className="flex items-end justify-between gap-4">
            <div className="space-y-1">
              {title && (
                <div className="flex items-center gap-3">
                  <h1 className="font-display font-bold text-[36px] uppercase text-ink leading-tight">
                    {title}
                  </h1>
                  {badge}
                </div>
              )}
              {subtitle && (
                <p className="font-body text-steel text-[14.5px]">{subtitle}</p>
              )}
            </div>
            {toolbar && <div className="flex items-center gap-2">{toolbar}</div>}
          </div>
        )}

        {filters && <div>{filters}</div>}

        <div>{children}</div>
      </div>
    </div>
  );
}
