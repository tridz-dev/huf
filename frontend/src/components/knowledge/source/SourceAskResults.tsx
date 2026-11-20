/** State D of the source page: the passages an ask returned, as ResultCards. */
import { useCallback, useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { ResultCard, ResultsNote } from '@/components/patterns';
import { testSearch } from '@/services/knowledgeApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';
import { dedupeLines, locationOf, matchLevels, normalizeResults, type TestResult } from '../import/testSearchHelpers';

export function useSourceAsk(source: KnowledgeSourceDoc) {
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<TestResult[] | null>(null);
  const [asked, setAsked] = useState('');
  const [error, setError] = useState<string | null>(null);

  const blocked =
    source.status === 'Error'
      ? 'Search is not working for this source. Open Settings or rebuild the search index.'
      : null;

  const run = useCallback(
    async (q: string) => {
      const text = q.trim();
      if (!text || blocked) return;
      setSearching(true);
      setError(null);
      setAsked(text);
      try {
        setResults(normalizeResults(await testSearch(source.name, text, 5)));
      } catch (e) {
        setResults(null);
        setError(getFrappeErrorMessage(e) || 'We could not run that search. Try again.');
      } finally {
        setSearching(false);
      }
    },
    [source.name, blocked],
  );

  const clear = useCallback(() => {
    setResults(null);
    setAsked('');
    setError(null);
  }, []);

  return { run, clear, searching, results, asked, error, blocked };
}

export interface SourceAskResultsProps {
  asked: string;
  searching: boolean;
  results: TestResult[] | null;
  error: string | null;
  blocked: string | null;
  onClear: () => void;
  onOpenDocument: (r: TestResult) => void;
}

function typeOf(name: string): string | undefined {
  const m = /\.([a-z0-9]{2,5})$/i.exec(name.trim());
  return m ? m[1].toUpperCase() : undefined;
}

export function SourceAskResults({ asked, searching, results, error, blocked, onClear, onOpenDocument }: SourceAskResultsProps) {
  if (blocked) return <p className="text-ui-text text-steel">{blocked}</p>;
  if (searching) {
    return (
      <div className="space-y-3" aria-busy="true" data-testid="ask-loading">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    );
  }
  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }
  if (results === null) return null;
  if (results.length === 0) {
    return (
      <div className="space-y-2">
        <ResultsNote onClear={onClear}>No passages found.</ResultsNote>
        <p className="py-4 text-center text-ui-text text-steel">Nothing matched. Try different words.</p>
      </div>
    );
  }
  // Honest strength: matchLevels already handles vector vs keyword score scales; no raw score is shown.
  const levels = matchLevels(results);
  return (
    <div className="space-y-3">
      <ResultsNote onClear={onClear}>These are the passages your agents would read.</ResultsNote>
      {results.map((r, i) => {
        const name = r.input_title || r.title || 'Untitled document';
        return (
          <ResultCard
            key={r.chunk_id ?? i}
            title={name}
            type={typeOf(name)}
            location={locationOf(r) || undefined}
            snippet={dedupeLines(String(r.text ?? ''))}
            query={asked}
            match={levels[i]}
            onOpen={() => onOpenDocument(r)}
            openLabel="Open document"
          />
        );
      })}
    </div>
  );
}
