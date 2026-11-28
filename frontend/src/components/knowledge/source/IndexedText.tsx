import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { getInputChunks, type InputChunksPage } from './inputsApi';

interface IndexedTextProps {
  knowledgeInput: string;
  /** Changes when the input is (re)indexed, so the text is fetched again. */
  version: string;
  /** Only an indexed input has text to show. */
  indexed: boolean;
}

function pageLabel(page?: number | null, end?: number | null): string | null {
  if (!page) return null;
  return end && end > page ? `Pages ${page}-${end}` : `Page ${page}`;
}

/** The text the search index holds for one document, one page of sections at a time. */
export function IndexedText({ knowledgeInput, version, indexed }: IndexedTextProps) {
  const [start, setStart] = useState(0);
  const [data, setData] = useState<InputChunksPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => setStart(0), [knowledgeInput, version]);

  useEffect(() => {
    if (!indexed) return;
    let alive = true;
    setLoading(true);
    setError(null);
    getInputChunks(knowledgeInput, start)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(getFrappeErrorMessage(e) || 'Could not load the indexed text'))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [knowledgeInput, version, indexed, start]);

  let body;
  if (!indexed) body = <p className="text-sm text-steel">Nothing is indexed yet. The text appears here once this document is added.</p>;
  else if (error) body = <p role="alert" className="text-sm text-steel">{error}</p>;
  else if (!data) body = <Skeleton className="h-24 w-full" />;
  else if (!data.supported) {
    body = <p className="text-sm text-steel">This source&apos;s search store cannot show the indexed text. The original is still available above.</p>;
  } else if (data.total === 0) body = <p className="text-sm text-steel">No text was indexed for this document.</p>;
  else {
    const last = Math.min(data.start + data.chunks.length, data.total);
    body = (
      <>
        <ol className="space-y-3" aria-busy={loading}>
          {data.chunks.map((c) => (
            <li key={c.index} className="rounded border border-line bg-paper-deep p-3">
              <div className="mb-1 text-meta text-steel-soft">
                Section {c.index + 1}
                {pageLabel(c.page, c.page_end) ? ` · ${pageLabel(c.page, c.page_end)}` : ''}
              </div>
              <p className="whitespace-pre-wrap break-words text-sm text-ink" data-testid="indexed-chunk">{c.text}</p>
            </li>
          ))}
        </ol>
        <div className="mt-3 flex items-center justify-between text-meta text-steel">
          <span>
            {(data.start + 1).toLocaleString()}-{last.toLocaleString()} of {data.total.toLocaleString()} sections
          </span>
          <span className="flex gap-2">
            <Button type="button" size="sm" variant="outline" disabled={loading || data.start === 0} onClick={() => setStart(Math.max(0, data.start - data.limit))}>
              Previous
            </Button>
            <Button type="button" size="sm" variant="outline" disabled={loading || last >= data.total} onClick={() => setStart(data.start + data.limit)}>
              Next
            </Button>
          </span>
        </div>
      </>
    );
  }

  return (
    <section className="mt-6" aria-label="Indexed text" data-testid="indexed-text">
      <h3 className="mb-2 text-sm font-medium text-ink">Indexed text</h3>
      {body}
    </section>
  );
}
