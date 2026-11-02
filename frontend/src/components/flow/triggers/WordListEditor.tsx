import { useState } from 'react';
import { X } from 'lucide-react';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';

/**
 * A list of words or names, typed one at a time ("order", "refund"). Enter or a comma adds; each word has a remove button.
 * Used for words to look for, commands, buttons and the people a trigger is limited to.
 */
export function WordListEditor({
  id, testId, words, onChange, placeholder, label,
}: { id: string; testId: string; words: string[]; onChange: (next: string[]) => void; placeholder?: string; label: string }) {
  const [draft, setDraft] = useState('');
  const add = (raw: string) => {
    const incoming = raw.split(',').map((w) => w.trim()).filter(Boolean).filter((w) => !words.some((x) => x.toLowerCase() === w.toLowerCase()));
    setDraft('');
    if (incoming.length) onChange([...words, ...incoming]);
  };
  return (
    <div className="space-y-2" data-testid={`${testId}-editor`}>
      {words.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5" aria-label={label}>
          {words.map((w, i) => (
            <li key={`${w}-${i}`} className="inline-flex max-w-full items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-sm" data-testid={`${testId}-word-${i}`}>
              <span className="truncate">{w}</span>
              <button
                type="button"
                className="rounded-full p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label={`Remove ${w}`}
                data-testid={`${testId}-remove-${i}`}
                onClick={() => onChange(words.filter((_, j) => j !== i))}
              >
                <X className="h-3 w-3" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex gap-2">
        <Input
          id={id}
          data-testid={testId}
          value={draft}
          placeholder={placeholder}
          onChange={(e) => (e.target.value.endsWith(',') ? add(e.target.value) : setDraft(e.target.value))}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              add(draft);
            }
          }}
          onBlur={() => draft.trim() && add(draft)}
        />
        <Button type="button" variant="outline" size="sm" data-testid={`${testId}-add`} disabled={!draft.trim()} onClick={() => add(draft)}>
          Add
        </Button>
      </div>
    </div>
  );
}
