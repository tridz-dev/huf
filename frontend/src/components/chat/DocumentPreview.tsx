/**
 * DocumentPreview — renders a saved document artifact as a white "paper" page.
 *
 * Fetches fully self-contained HTML (inline styles + fonts) from the backend
 * and renders it inside a sandboxed iframe. The sandbox intentionally omits
 * `allow-scripts`: the HTML is model-authored and must never execute script
 * inside the app. The surrounding container keeps the chat's normal
 * background so the white page visibly sits on top of it, like paper.
 */
import { useEffect, useState } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';
import { getArtifactHtml } from '@/services/artifactApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { cn } from '@/lib/utils';

interface DocumentPreviewProps {
  artifactName: string;
  className?: string;
}

export function DocumentPreview({ artifactName, className }: DocumentPreviewProps) {
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError(null);
    setHtml(null);

    getArtifactHtml(artifactName)
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

    return () => {
      cancelled = true;
    };
  }, [artifactName]);

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
    <div className={cn('flex justify-center py-4', className)}>
      <iframe
        srcDoc={html}
        sandbox="allow-same-origin"
        title="Document preview"
        className="w-full max-w-[820px] rounded-lg border shadow-md bg-white"
        style={{ aspectRatio: '210 / 297', minHeight: '1000px' }}
      />
    </div>
  );
}
