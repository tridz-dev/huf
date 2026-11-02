import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { filterChoices } from './model';

/** Searchable record-type picker (themed with the Telegram palette, no portals). */
export function DoctypePicker({ choices, value, onChange }: {
  choices: string[]; value: string; onChange: (v: string) => void;
}) {
  const [query, setQuery] = useState(value);
  const [open, setOpen] = useState(false);
  const matches = filterChoices(choices, query);
  return (
    <div className="relative">
      <Input
        role="combobox"
        aria-expanded={open}
        aria-label="Record type"
        placeholder="What are you looking for?"
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(e) => { setQuery(e.target.value); onChange(''); setOpen(true); }}
      />
      {open && matches.length ? (
        <ul role="listbox" className="absolute z-10 mt-1 max-h-56 w-full overflow-auto rounded-md border bg-[var(--tg-bg)] text-sm shadow">
          {matches.map((c) => (
            <li key={c} role="option" aria-selected={c === value}>
              <button
                type="button"
                className="w-full px-3 py-2 text-left"
                onClick={() => { onChange(c); setQuery(c); setOpen(false); }}
              >
                {c}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {open && query.trim() && !matches.length ? (
        <p className="mt-1 text-xs text-[var(--tg-hint)]">Nothing matches that.</p>
      ) : null}
    </div>
  );
}
