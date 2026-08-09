/**
 * DocumentPreview — renders a document artifact as a white "paper" page.
 *
 * Two modes:
 *  - Durable: pass `artifactName` for a saved Artifact row. Fetches
 *    self-contained HTML (inline styles + fonts) via get_artifact_html.
 *  - Transient: pass `content` (+ optional `language`/`title`) for content
 *    that has no Artifact row yet — either parsed inline from a chat message
 *    that was never persisted, or (in principle) content still being
 *    composed. Renders via preview_document_html instead.
 *
 * Either way the HTML lands in a sandboxed iframe. The sandbox intentionally
 * omits `allow-scripts`: the HTML is model-authored and must never execute
 * script inside the app. The surrounding container keeps the chat's normal
 * background so the white page visibly sits on top of it, like paper.
 *
 * Debounce rationale (transient mode only): the artifact parser
 * (artifactParser.ts) only ever emits an artifact once its closing
 * </artifact> tag has streamed in — a still-open block stays as raw text and
 * never reaches this component, so there's no need to detect "in-progress"
 * content here. However the parser also mints a fresh id
 * (`artifact-${Date.now()}-${index}`) on every parse, so this component gets
 * remounted (new React key upstream) on every re-render of the surrounding
 * message for as long as the rest of the message keeps streaming after the
 * artifact block closes. A plain per-mount fetch would therefore still hit
 * the endpoint on most tokens. Debouncing the transient fetch behind a short
 * timer means rapid remounts keep cancelling and rescheduling it, so the
 * network call only fires once the message settles for a beat — without
 * needing to touch the id scheme in artifactParser.ts.
 */
import { useEffect, useState } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';
import { getArtifactHtml, previewDocumentHtml } from '@/services/artifactApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { cn } from '@/lib/utils';

const PREVIEW_DEBOUNCE_MS = 500;

interface DocumentPreviewProps {
  /** Durable mode: name of a saved Artifact row. */
  artifactName?: string;
  /** Transient mode: unsaved content to render directly. */
  content?: string;
  language?: string;
  title?: string;
  className?: string;
}

export function DocumentPreview({
  artifactName,
  content,
  language,
  title,
  className,
}: DocumentPreviewProps) {
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError(null);
    setHtml(null);

    const load = () => {
      const request = artifactName
        ? getArtifactHtml(artifactName)
        : previewDocumentHtml(content ?? '', language, title);

      request
        .then((result) => {
          if (!cancelled) {
            setHtml(result);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            setError(getFrappeErrorMessage(err));
          }
        })
        .finally(() => {
          if (!cancelled) {
            setLoading(false);
          }
        });
    };

    if (artifactName) {
      // Durable artifacts are stable and rarely remounted — fetch right away.
      load();
    } else if (content) {
      // Transient content: debounce so a burst of remounts (see file-level
      // comment) collapses into a single request once things settle.
      const timer = setTimeout(load, PREVIEW_DEBOUNCE_MS);
      return () => {
        cancelled = true;
        clearTimeout(timer);
      };
    } else {
      setLoading(false);
    }

    return () => {
      cancelled = true;
    };
  }, [artifactName, content, language, title]);

  if (loading) {
    return (
      <div className={cn('flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground', className)}>
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading document…
      </div>
    );
  }

  if (error || html === null) {
    return (
      <div
        className={cn(
          'flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive',
          className
        )}
      >
        <AlertCircle className="h-4 w-4 shrink-0" />
        <span>{error || 'Unable to render this document.'}</span>
      </div>
    );
  }

  return (
    <div className={cn('flex justify-center px-4 py-4', className)}>
      <iframe
        srcDoc={html}
        sandbox="allow-same-origin"
        title="Document preview"
        className="w-full flex-1 rounded border bg-panel"
        style={{ aspectRatio: '210 / 297', minHeight: '1000px' }}
      />
    </div>
  );
}
