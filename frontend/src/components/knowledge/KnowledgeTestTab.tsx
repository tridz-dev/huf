import { useEffect, useState } from 'react';
import { AlertCircle, Search } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { getKnowledgeInputs, testSearch } from '@/services/knowledgeApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';
import {
  MATCH_LABEL,
  highlightParts,
  locationOf,
  matchLevels,
  normalizeResults,
  type TestResult,
} from './import/testSearchHelpers';

const LEVEL_VARIANT = { high: 'default', good: 'secondary', weak: 'outline' } as const;

function openDocuments() {
  window.location.hash = 'documents';
}

/** Test tab: ask a question and see which documents would answer it. */
export function KnowledgeTestTab({ source }: { source: KnowledgeSourceDoc | null }) {
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(5);
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<TestResult[] | null>(null);
  const [asked, setAsked] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [docCount, setDocCount] = useState<number | null>(null);

  const sourceName = source?.name;
  useEffect(() => {
    if (!sourceName) return;
    let alive = true;
    getKnowledgeInputs(sourceName)
      .then((rows) => {
        if (!alive) return;
        setDocCount(rows.length);
        const titles = rows
          .filter((r) => r.status === 'Indexed')
          .map((r) => (r.title || r.file_name || '').trim())
          .filter(Boolean);
        setSuggestions(titles.slice(0, 3));
      })
      .catch(() => alive && setDocCount(null));
    return () => {
      alive = false;
    };
  }, [sourceName]);

  const blocked = !source
    ? 'Save the source first.'
    : source.status === 'Error'
      ? 'Search is not working for this source. Open Settings or rebuild the search index.'
      : docCount === 0
        ? 'Add documents first, then you can test a question.'
        : null;

  const run = async (q = query, k = topK) => {
    if (!source || !q.trim() || blocked) return;
    setSearching(true);
    setError(null);
    try {
      setResults(normalizeResults(await testSearch(source.name, q.trim(), k)));
      setAsked(q.trim());
    } catch (e) {
      setError(getFrappeErrorMessage(e) || 'We could not run that search. Try again.');
    } finally {
      setSearching(false);
    }
  };

  const levels = results ? matchLevels(results) : [];
  const askButton = (
    <Button type="button" onClick={() => void run()} disabled={searching || !query.trim() || !!blocked}>
      <Search className="mr-2 h-4 w-4" />
      Ask
    </Button>
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ask a question your agents might get</CardTitle>
        <CardDescription>See which documents would answer it, and how well.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <TooltipProvider>
          <div className="flex items-center gap-2">
            <Input
              placeholder="What is the refund policy for annual plans?"
              value={query}
              disabled={!!blocked}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  void run();
                }
              }}
            />
            {blocked ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span tabIndex={0}>{askButton}</span>
                </TooltipTrigger>
                <TooltipContent>{blocked}</TooltipContent>
              </Tooltip>
            ) : (
              askButton
            )}
          </div>
          {blocked && <p className="text-sm text-steel">{blocked}</p>}
          {!blocked && suggestions.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 text-sm text-steel">
              <span>Try:</span>
              {suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="rounded-full border px-2 py-0.5 hover:bg-muted"
                  onClick={() => {
                    setQuery(s);
                    void run(s);
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          {searching && (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          )}
          {!searching && !error && results !== null && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">Best matches ({results.length})</p>
                <div className="flex items-center gap-2 text-sm text-steel">
                  Show:
                  <Select
                    value={String(topK)}
                    onValueChange={(v) => {
                      const k = Number(v);
                      setTopK(k);
                      if (asked) void run(asked, k);
                    }}
                  >
                    <SelectTrigger className="w-28">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="5">Top 5</SelectItem>
                      <SelectItem value="10">Top 10</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              {results.length === 0 ? (
                <p className="py-4 text-center text-sm text-steel">
                  Nothing matched. Try different words, or check that documents finished importing.{' '}
                  <button type="button" className="underline" onClick={openDocuments}>
                    Go to Documents
                  </button>
                </p>
              ) : (
                results.map((r, i) => {
                  const loc = locationOf(r);
                  const name = r.input_title || r.title || 'Untitled document';
                  return (
                    <div key={r.chunk_id ?? i} className="space-y-1 rounded-md border p-3">
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-sm font-medium">
                          {i + 1}. {name}
                          {loc ? `, ${loc}` : ''}
                        </p>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Badge variant={LEVEL_VARIANT[levels[i]]} size="sm">
                              {MATCH_LABEL[levels[i]]}
                            </Badge>
                          </TooltipTrigger>
                          <TooltipContent>
                            Score {typeof r.score === 'number' ? r.score.toFixed(3) : 'n/a'}
                          </TooltipContent>
                        </Tooltip>
                      </div>
                      <p className="whitespace-pre-wrap text-sm text-steel">
                        {highlightParts(String(r.text ?? '').slice(0, 400), asked).map((p, j) =>
                          p.hit ? (
                            <mark key={j} className="rounded bg-yellow-200 px-0.5 text-foreground dark:bg-yellow-700">
                              {p.text}
                            </mark>
                          ) : (
                            <span key={j}>{p.text}</span>
                          ),
                        )}
                      </p>
                      <button type="button" className="text-xs underline" onClick={openDocuments}>
                        Open document
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </TooltipProvider>
      </CardContent>
    </Card>
  );
}
