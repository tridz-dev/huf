/**
 * AskField (DESIGN.md §6.10.3): the collection's one search box. It searches
 * or asks in the same field, shows a "/" key hint, and "/" anywhere on the
 * page (outside an editable element) focuses it.
 */
import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { Search, X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { ShortcutKey } from '@/components/ui/shortcut-key';
import { cn } from '@/lib/utils';

export interface AskFieldProps {
  value: string;
  onChange: (value: string) => void;
  /** Called on Enter: run the search / ask. */
  onSubmit?: (value: string) => void;
  placeholder?: string;
  /** Accessible name. Defaults to the placeholder. */
  label?: string;
  /** Bind the page-wide "/" shortcut. Turn off when two fields share a page. */
  shortcut?: boolean;
  className?: string;
}

/** True when a keystroke target already accepts text, so "/" must type, not jump. */
export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

export const AskField = forwardRef<HTMLInputElement, AskFieldProps>(function AskField(
  { value, onChange, onSubmit, placeholder = 'Search…', label, shortcut = true, className },
  ref,
) {
  const inner = useRef<HTMLInputElement>(null);
  useImperativeHandle(ref, () => inner.current as HTMLInputElement);

  useEffect(() => {
    if (!shortcut) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey || isEditableTarget(e.target)) return;
      e.preventDefault();
      inner.current?.focus();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [shortcut]);

  return (
    <div role="search" className={cn('relative flex w-full items-center', className)}>
      <Search aria-hidden="true" className="pointer-events-none absolute left-3 h-4 w-4 text-steel-soft" />
      <Input
        ref={inner}
        type="search"
        size="lg"
        value={value}
        placeholder={placeholder}
        aria-label={label ?? placeholder}
        aria-keyshortcuts={shortcut ? '/' : undefined}
        className="bg-panel pl-9 pr-16 [&::-webkit-search-cancel-button]:hidden"
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') onSubmit?.(value);
          if (e.key === 'Escape' && value) {
            e.preventDefault();
            onChange('');
          }
        }}
      />
      <span className="absolute right-3 flex items-center gap-2">
        {value && (
          <button
            type="button"
            aria-label="Clear search"
            onClick={() => {
              onChange('');
              inner.current?.focus();
            }}
            className="rounded-sm text-steel-soft hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
        {shortcut && !value && <ShortcutKey size="sm">/</ShortcutKey>}
      </span>
    </div>
  );
});
