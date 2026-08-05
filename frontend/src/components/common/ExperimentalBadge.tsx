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
        'inline-flex items-center gap-1.5 rounded border border-line bg-panel/60 font-mono uppercase tracking-wider text-steel-soft select-none font-medium',
        size === 'sm' ? 'px-1.5 py-0.5 text-[9px]' : 'px-2 py-0.5 text-[10px]',
        className
      )}
    >
      <FlaskConical className={cn(size === 'sm' ? 'size-2.5' : 'size-3', 'shrink-0 opacity-70')} strokeWidth={1.5} />
      <span>Experimental</span>
    </span>
  );
}

export default ExperimentalBadge;

