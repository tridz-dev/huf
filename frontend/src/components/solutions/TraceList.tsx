import { cn } from '@/lib/utils';
import type { TraceLine } from './useTestChat';

const STYLES: Record<TraceLine['k'], string> = {
  win: 'border-primary bg-primary/10 text-foreground font-medium',
  skip: 'border-border text-steel',
  info: 'border-border bg-muted text-steel',
};

const MARKS: Record<TraceLine['k'], string> = { win: 'Won', skip: 'Skipped', info: 'Note' };

export function TraceList({ trace }: { trace: TraceLine[] }) {
  if (trace.length === 0) {
    return <p className="text-sm text-steel">Send a message to see how it was routed.</p>;
  }
  return (
    <ul className="flex flex-col gap-1.5" aria-label="Routing trace">
      {trace.map((line, i) => (
        <li
          key={i}
          data-kind={line.k}
          className={cn('rounded-md border-l-2 px-2.5 py-1.5 text-sm', STYLES[line.k])}
        >
          <span className="sr-only">{MARKS[line.k]}: </span>
          {line.t}
        </li>
      ))}
    </ul>
  );
}
