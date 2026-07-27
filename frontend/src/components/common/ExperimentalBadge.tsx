import { FlaskConical } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ExperimentalBadgeProps {
  className?: string;
  size?: 'sm' | 'md';
}

export function ExperimentalBadge({ className, size = 'md' }: ExperimentalBadgeProps) {
  return (
    <span
      title="Experimental feature"
      aria-label="Experimental feature"
      className={cn(
        'inline-flex items-center gap-1.5 rounded-none border border-amber-500/40 bg-amber-500/10 font-mono uppercase tracking-wider text-amber-600 dark:text-amber-400 select-none font-medium',
        size === 'sm' ? 'px-1.5 py-0.5 text-[9px]' : 'px-2 py-0.5 text-[10.5px]',
        className
      )}
    >
      <FlaskConical className={cn(size === 'sm' ? 'size-2.5' : 'size-3.5', 'shrink-0')} strokeWidth={1.8} />
      <span>Experimental</span>
    </span>
  );
}

export default ExperimentalBadge;

