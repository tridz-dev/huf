/**
 * ResultCard (DESIGN.md §6.10.7): one passage returned by a search or ask —
 * where it came from, the passage with the matched words marked, a match
 * strength word, and an Open action. Results are a list of these under a
 * one-line note saying what they are ("These are the passages … would read").
 */
import type { ReactNode } from 'react';
import { ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { TypeGlyph } from './ResourceList';

export type MatchStrength = 'high' | 'good' | 'weak';

const MATCH: Record<MatchStrength, { label: string; variant: 'pill-success' | 'pill-info' | 'pill-neutral' }> = {
  high: { label: 'High match', variant: 'pill-success' },
  good: { label: 'Good match', variant: 'pill-info' },
  weak: { label: 'Weak match', variant: 'pill-neutral' },
};

/** Map a 0..1 score to a word. Thresholds are a product decision; keep them here. */
export function matchStrength(score: number): MatchStrength {
  if (score >= 0.75) return 'high';
  if (score >= 0.5) return 'good';
  return 'weak';
}

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Wrap each query term (3+ chars, case-insensitive) in <mark>. Plain text in, nodes out: never HTML. */
export function highlightTerms(text: string, query: string): ReactNode[] {
  const terms = Array.from(new Set(query.toLowerCase().split(/\s+/).filter((t) => t.length >= 3)));
  if (terms.length === 0) return [text];
  const re = new RegExp(`(${terms.map(escapeRe).join('|')})`, 'gi');
  return text.split(re).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="rounded-sm bg-signal/15 px-0.5 text-ink">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

export interface ResultCardProps {
  title: string;
  type?: string;
  /** Location inside the item, e.g. "page 3" or 'section "Billing"'. */
  location?: ReactNode;
  snippet: string;
  /** Terms to mark in the snippet. */
  query?: string;
  match?: MatchStrength;
  onOpen?: () => void;
  openLabel?: string;
  className?: string;
}

export function ResultCard({ title, type, location, snippet, query = '', match, onOpen, openLabel = 'Open', className }: ResultCardProps) {
  const m = match ? MATCH[match] : null;
  return (
    <article data-testid="result-card" className={cn('rounded border border-line bg-panel p-4', className)}>
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {type && <TypeGlyph label={type} />}
        <h3 className="min-w-0 truncate text-ui-text font-semibold text-ink">{title}</h3>
        {location && <span className="font-mono text-meta text-steel-soft">{location}</span>}
        <span className="flex-1" />
        {m && <Badge variant={m.variant}>{m.label}</Badge>}
      </header>
      <p className="mt-2 text-ui-text leading-relaxed text-steel">{highlightTerms(snippet, query)}</p>
      {onOpen && (
        <Button type="button" variant="link" size="sm" className="mt-1 px-0" onClick={onOpen}>
          {openLabel}
          <ExternalLink aria-hidden="true" className="h-3 w-3" />
        </Button>
      )}
    </article>
  );
}

/** The one-line caption above a result list, with an optional "Clear search". */
export function ResultsNote({ children, onClear, clearLabel = 'Clear search' }: { children: ReactNode; onClear?: () => void; clearLabel?: string }) {
  return (
    <div className="flex items-center gap-2 text-micro text-steel" role="status">
      <span className="min-w-0">{children}</span>
      <span className="flex-1" />
      {onClear && (
        <Button type="button" variant="link" size="sm" onClick={onClear}>
          {clearLabel}
        </Button>
      )}
    </div>
  );
}
