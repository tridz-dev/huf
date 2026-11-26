/**
 * ArtifactPaneBody — body of the artifact side pane, chosen by artifact type.
 *
 * Document/markdown artifacts keep `DocumentPreview` (server-rendered HTML).
 * Every other type (chart, jsx, mermaid, code, html, ...) is fetched by name
 * and drawn by the shared `ArtifactRenderer`, because the document export
 * endpoint refuses non-document artifacts.
 */
import { useEffect, useState } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';
import { DocumentPreview } from '@/components/chat/DocumentPreview';
import { ArtifactRenderer } from '@/components/chat/ArtifactRenderer';
import { isDocumentType } from '@/components/chat/ArtifactsPanel';
import { getArtifact, type ArtifactDoc } from '@/services/artifactApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { ArtifactType, ParsedArtifact } from '@/types/artifact.types';

const RENDERER_TYPES = new Set<string>([
  'code', 'document', 'html', 'svg', 'mermaid', 'react-component',
  'markdown', 'jsx', 'chart', 'video',
]);

export function toParsedArtifact(doc: ArtifactDoc): ParsedArtifact {
  return {
    id: doc.name,
    // Backend-only types (image, text, ...) fall to the renderer's default case.
    type: (RENDERER_TYPES.has(doc.artifact_type) ? doc.artifact_type : 'document') as ArtifactType,
    title: doc.title,
    language: doc.language,
    content: doc.content,
  };
}

function RendererBody({ name }: { name: string }) {
  const [doc, setDoc] = useState<ArtifactDoc | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDoc(null);
    setError(null);
    getArtifact(name)
      .then((d) => {
        if (!cancelled) setDoc(d);
      })
      .catch((e) => {
        if (!cancelled) setError(getFrappeErrorMessage(e) || 'Failed to load artifact');
      });
    return () => {
      cancelled = true;
    };
  }, [name]);

  if (error) {
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-steel" role="alert">
        <AlertCircle className="size-4" />
        {error}
      </div>
    );
  }
  if (!doc) {
    return (
      <div className="flex justify-center p-6 text-steel" data-testid="artifact-pane-loading">
        <Loader2 className="size-5 animate-spin" />
      </div>
    );
  }
  return (
    <div className="p-3">
      <ArtifactRenderer artifact={toParsedArtifact(doc)} />
    </div>
  );
}

export function ArtifactPaneBody({ name, artifactType }: { name: string; artifactType: string }) {
  if (isDocumentType(artifactType)) {
    return <DocumentPreview artifactName={name} />;
  }
  return <RendererBody name={name} />;
}
