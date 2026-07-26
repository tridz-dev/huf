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
        'relative h-full',
        hover && 'transition-colors',
        onClick && 'cursor-pointer',
        hover && onClick && 'hover:border-ink',
        className
      )}
      onClick={onClick}
    >
      {children}
    </Card>
  );
}
