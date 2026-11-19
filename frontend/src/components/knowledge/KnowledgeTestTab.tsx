import { useState } from 'react';
import { AlertCircle, Loader2, Search } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { testSearch } from '@/services/knowledgeApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';

interface TestSearchResultChunk {
  text?: string;
  content?: string;
  score?: number;
  relevance?: number;
  source?: string;
  file_name?: string;
  [key: string]: unknown;
}

function normalizeTestSearchResults(raw: unknown): TestSearchResultChunk[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw as TestSearchResultChunk[];
  if (typeof raw === 'object') {
    const obj = raw as Record<string, unknown>;
    if (Array.isArray(obj.results)) return obj.results as TestSearchResultChunk[];
    if (Array.isArray(obj.chunks)) return obj.chunks as TestSearchResultChunk[];
  }
  return [];
}

/** Test tab. Placeholder search box; the richer panel replaces its internals later. */
export function KnowledgeTestTab({ source }: { source: KnowledgeSourceDoc | null }) {
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<TestSearchResultChunk[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    if (!source || !query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      setResults(normalizeTestSearchResults(await testSearch(source.name, query.trim())));
    } catch (e) {
      setError(getFrappeErrorMessage(e) || 'We could not run that search. Try again.');
    } finally {
      setSearching(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Test a question</CardTitle>
        <CardDescription>Ask something your agents might get and see what they would find.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2">
          <Input
            placeholder="Ask a question..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                void run();
              }
            }}
          />
          <Button type="button" onClick={() => void run()} disabled={searching || !query.trim()}>
            {searching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}
            Search
          </Button>
        </div>
        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {!error && results !== null &&
          (results.length === 0 ? (
            <p className="py-4 text-center text-sm text-steel">No matching results found.</p>
          ) : (
            <div className="space-y-2">
              {results.map((r, i) => {
                const score = r.score ?? r.relevance;
                const label = r.file_name ?? r.source;
                return (
                  <div key={i} className="space-y-1 rounded-md border p-3">
                    <div className="flex items-center justify-between gap-2">
                      {label ? <p className="truncate text-xs font-medium text-steel">{String(label)}</p> : <span />}
                      {typeof score === 'number' && (
                        <Badge variant="outline" size="sm">
                          score {score.toFixed(3)}
                        </Badge>
                      )}
                    </div>
                    <p className="whitespace-pre-wrap text-sm">{String(r.text ?? r.content ?? '')}</p>
                  </div>
                );
              })}
            </div>
          ))}
      </CardContent>
    </Card>
  );
}
