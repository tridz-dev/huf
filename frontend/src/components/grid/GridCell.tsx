/**
 * GridCell (DESIGN.md §6.11.3): read display and in-cell editor for each
 * column type. Editors are the shared ui primitives at the dense `sm` size,
 * borderless inside the cell; the cell itself draws the focus ring.
 */
import { useEffect, useRef, type KeyboardEvent } from 'react';
import { ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { TONE_PILL, formatCell, isNumeric, type CellValue, type GridColumn } from './types';

export function CellDisplay<R>({ col, value, onToggle }: { col: GridColumn<R>; value: CellValue; onToggle?: (v: boolean) => void }) {
  if (col.type === 'checkbox') {
    return (
      <Checkbox
        tabIndex={-1}
        checked={Boolean(value)}
        disabled={col.readOnly || !onToggle}
        onCheckedChange={(v) => onToggle?.(v === true)}
        aria-label={col.label}
      />
    );
  }
  const text = formatCell(col, value);
  if (!text) return null;
  if (col.type === 'select') {
    const tone = col.options?.find((o) => o.value === value)?.tone ?? 'neutral';
    return <Badge variant={TONE_PILL[tone]}>{text}</Badge>;
  }
  if (col.type === 'link') {
    return (
      <span className="inline-flex min-w-0 items-center gap-1 text-signal-ink">
        <span className="truncate">{text}</span>
        <ExternalLink aria-hidden="true" className="h-3 w-3 shrink-0 opacity-60" />
      </span>
    );
  }
  return <span className={cn('block truncate', isNumeric(col.type) && 'text-right tabular-nums')}>{text}</span>;
}

export interface CellEditorProps<R> {
  col: GridColumn<R>;
  draft: string;
  onDraft: (v: string) => void;
  /** Commit the draft; `dir` is where the active cell moves next. */
  onCommit: (dir: 'down' | 'right' | 'left' | 'none', value?: string) => void;
  onCancel: () => void;
  invalid?: boolean;
  describedBy?: string;
}

const EDITOR = 'h-full w-full rounded-none border-0 bg-panel px-3 shadow-none focus-visible:ring-0';

export function CellEditor<R>({ col, draft, onDraft, onCommit, onCancel, invalid, describedBy }: CellEditorProps<R>) {
  const ref = useRef<HTMLInputElement & HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.focus();
    if (typeof el.setSelectionRange === 'function' && col.type !== 'date' && !isNumeric(col.type)) {
      el.setSelectionRange(el.value.length, el.value.length);
    }
  }, [col.type]);

  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      onCancel();
    } else if (e.key === 'Enter' && !(col.type === 'longtext' && e.shiftKey)) {
      e.preventDefault();
      e.stopPropagation();
      onCommit('down');
    } else if (e.key === 'Tab') {
      e.preventDefault();
      e.stopPropagation();
      onCommit(e.shiftKey ? 'left' : 'right');
    }
  };

  const common = {
    'aria-label': col.label,
    'aria-invalid': invalid || undefined,
    'aria-describedby': describedBy,
    onKeyDown: onKey,
  };

  if (col.type === 'select') {
    return (
      <Select
        defaultOpen
        value={draft || undefined}
        onValueChange={(v) => onCommit('none', v)}
        onOpenChange={(open) => !open && onCancel()}
      >
        <SelectTrigger size="sm" className={EDITOR} aria-label={col.label}>
          <SelectValue placeholder="Choose…" />
        </SelectTrigger>
        <SelectContent>
          {(col.options ?? []).map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label ?? o.value}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }
  if (col.type === 'longtext') {
    return <Textarea ref={ref} {...common} value={draft} onChange={(e) => onDraft(e.target.value)} className={cn(EDITOR, 'min-h-24 py-2')} />;
  }
  return (
    <Input
      ref={ref}
      {...common}
      size="sm"
      type={col.type === 'date' ? 'date' : 'text'}
      inputMode={isNumeric(col.type) ? 'decimal' : undefined}
      value={draft}
      onChange={(e) => onDraft(e.target.value)}
      onBlur={() => onCommit('none')}
      className={cn(EDITOR, isNumeric(col.type) && 'text-right tabular-nums')}
    />
  );
}
