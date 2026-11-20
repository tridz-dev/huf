/**
 * DropZone + StepHint (DESIGN.md §6.10.8): the empty state of a collection
 * that is filled by adding things. A three-step hint above (where am I in
 * the setup) and a dashed drop target below with the primary and secondary
 * add actions. The drop target also works as a click/keyboard target.
 */
import { useRef, useState, type ReactNode } from 'react';
import { Upload, type LucideIcon } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

export interface DropZoneProps {
  title: string;
  /** Accepted types and limits, plain words: "PDF, Word and Markdown. Up to 50 MB each." */
  hint?: string;
  /** Called with dropped or chosen files. Omit to make the zone actions-only. */
  onFiles?: (files: File[]) => void;
  /** Value for the hidden file input's accept attribute, e.g. ".pdf,.docx". */
  accept?: string;
  icon?: LucideIcon;
  /** Buttons under the copy (primary add + e.g. "Connect storage"). */
  actions?: ReactNode;
  disabled?: boolean;
  className?: string;
}

export function DropZone({ title, hint, onFiles, accept, icon: Icon = Upload, actions, disabled, className }: DropZoneProps) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const take = (list: FileList | null) => {
    if (!list || list.length === 0 || disabled) return;
    onFiles?.(Array.from(list));
  };
  return (
    <div
      data-testid="drop-zone"
      data-state={over ? 'over' : undefined}
      onDragOver={(e) => {
        if (!onFiles) return;
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        if (!onFiles) return;
        e.preventDefault();
        setOver(false);
        take(e.dataTransfer.files);
      }}
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded border border-dashed px-6 py-12 text-center transition-colors',
        over ? 'border-signal bg-signal/5' : 'border-line bg-panel',
        disabled && 'pointer-events-none opacity-60',
        className,
      )}
    >
      <Icon aria-hidden="true" className="h-6 w-6 text-steel-soft" />
      {onFiles ? (
        <button
          type="button"
          onClick={() => input.current?.click()}
          className="rounded-sm text-subtitle text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {title}
        </button>
      ) : (
        <h2 className="text-subtitle text-ink">{title}</h2>
      )}
      {hint && <p className="max-w-[48ch] text-ui-text text-steel">{hint}</p>}
      {actions && <div className="mt-2 flex flex-wrap justify-center gap-2">{actions}</div>}
      {onFiles && (
        <Input
          ref={input}
          type="file"
          multiple
          accept={accept}
          tabIndex={-1}
          aria-hidden="true"
          className="hidden"
          onChange={(e) => {
            take(e.target.files);
            e.target.value = '';
          }}
        />
      )}
    </div>
  );
}

export interface Step {
  title: string;
  description?: string;
}

/** Numbered setup hint. `current` is 0-based; earlier steps read as done. */
export function StepHint({ steps, current = 0, className }: { steps: Step[]; current?: number; className?: string }) {
  return (
    <ol aria-label="Setup steps" className={cn('grid gap-3 sm:grid-cols-3', className)}>
      {steps.map((s, i) => (
        <li key={s.title} aria-current={i === current ? 'step' : undefined} className="flex items-start gap-3">
          <span
            className={cn(
              'flex h-6 w-6 shrink-0 items-center justify-center rounded-full border font-mono text-meta',
              i === current ? 'border-ink bg-ink text-primary-foreground' : i < current ? 'border-good text-good' : 'border-line text-steel',
            )}
          >
            {i + 1}
          </span>
          <span className="min-w-0">
            <span className={cn('block text-ui-text font-semibold', i === current ? 'text-ink' : 'text-steel')}>{s.title}</span>
            {s.description && <span className="block text-micro text-steel-soft">{s.description}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}
