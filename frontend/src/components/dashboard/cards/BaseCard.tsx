import { ReactNode } from 'react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface BaseCardProps {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
  hover?: boolean;
}

export function BaseCard({
  children,
  onClick,
  className,
  hover = true,
}: BaseCardProps) {
  return (
    <Card
      className={cn(
        'relative bg-card text-card-foreground rounded-md border shadow-sm',
        hover && 'transition-shadow',
        onClick && 'cursor-pointer',
        hover && onClick && 'hover:shadow-lg',
        className
      )}
      onClick={onClick}
    >
      {children}
    </Card>
  );
}
