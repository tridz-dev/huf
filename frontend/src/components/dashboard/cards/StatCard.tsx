import { ReactNode } from 'react';
import { LucideIcon } from 'lucide-react';
import { CardHeader, CardDescription, CardTitle, CardFooter, CardAction } from '@/components/ui/card';
import { BaseCard } from './BaseCard';

interface StatCardProps {
  title: string;
  value: string | number;
  description?: string;
  trend?: {
    value: string;
    direction: 'up' | 'down' | 'neutral';
  };
  icon?: LucideIcon;
  badge?: ReactNode;
  footer?: ReactNode;
  onClick?: () => void;
  className?: string;
}

export function StatCard({
  title,
  value,
  description,
  trend,
  icon: Icon,
  badge,
  footer,
  onClick,
  className,
}: StatCardProps) {
  return (
    <BaseCard onClick={onClick} className={className}>
      <CardHeader>
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-2xl font-semibold tabular-nums">
          {value}
        </CardTitle>
        {badge && <CardAction>{badge}</CardAction>}
      </CardHeader>
      {(footer || description || Icon) && (
        <CardFooter className="flex-col items-start gap-1.5 text-sm">
          {footer ? (
            footer
          ) : (
            <>
              {(description || Icon) && (
                <div className="line-clamp-1 flex gap-2 font-medium">
                  {description}
                  {Icon && <Icon className="w-4 h-4" />}
                </div>
              )}
              {trend && (
                <div className="text-muted-foreground">{trend.value}</div>
              )}
            </>
          )}
        </CardFooter>
      )}
    </BaseCard>
  );
}
