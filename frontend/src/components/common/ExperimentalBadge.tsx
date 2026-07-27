import { cn } from '@/lib/utils';

interface ExperimentalBadgeProps {
  className?: string;
  size?: 'sm' | 'md';
}

export function ExperimentalBadge({ className, size = 'md' }: ExperimentalBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-none border border-amber-500/40 bg-amber-500/10 font-mono uppercase tracking-wider text-amber-600 dark:text-amber-400 select-none font-medium',
        size === 'sm' ? 'px-1.5 py-0.5 text-[9px]' : 'px-2 py-0.5 text-[10.5px]',
        className
      )}
    >
      Experimental
    </span>
  );
}

export default ExperimentalBadge;
