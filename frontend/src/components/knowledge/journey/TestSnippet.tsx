import { useState } from 'react';
import { dedupeLines, highlightParts } from '../import/testSearchHelpers';

const MAX_LINES = 3;

/** Result snippet: duplicate lines collapsed, capped at about 3 lines with "Show more". */
export function TestSnippet({ text, query }: { text: string; query: string }) {
  const [open, setOpen] = useState(false);
  const lines = dedupeLines(text).split('\n');
  const long = lines.length > MAX_LINES || text.length > 400;
  const shown = open || !long ? lines.join('\n') : lines.slice(0, MAX_LINES).join('\n').slice(0, 400);
  return (
    <div>
      <p className="whitespace-pre-wrap text-sm text-steel">
        {highlightParts(shown, query).map((p, j) =>
          p.hit ? (
            <mark key={j} className="rounded bg-yellow-200 px-0.5 text-foreground dark:bg-yellow-700">
              {p.text}
            </mark>
          ) : (
            <span key={j}>{p.text}</span>
          ),
        )}
        {long && !open ? '…' : ''}
      </p>
      {long && (
        <button type="button" className="text-xs underline" onClick={() => setOpen((o) => !o)}>
          {open ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  );
}
