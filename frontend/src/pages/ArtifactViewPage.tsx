/**
 * Full-screen permalink page for a single artifact.
 *
 * Route: /artifact/:artifactId
 *
 * Unlike /view/:messageId (which re-parses a whole message and shows every
 * artifact it contains), this page fetches and renders exactly one artifact
 * by its stable id, so it can be shared/linked independently of its message.
 */

import { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Loader2, ExternalLink, AlertCircle, FileText, Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { getArtifact, exportArtifact, type ArtifactDoc } from '@/services/artifactApi';
import { ArtifactRenderer } from '@/components/chat/ArtifactRenderer';
import type { ParsedArtifact, ArtifactType } from '@/types/artifact.types';

/** artifact_type values the backend allows that the frontend renderer doesn't have a dedicated case for. */
const FRONTEND_ARTIFACT_TYPES = new Set<ArtifactType>([
  'code',
  'document',
  'html',
  'svg',
  'mermaid',
  'react-component',
  'markdown',
  'jsx',
  'chart',
  'video',
]);

/** Map a backend artifact_type to a type the frontend ArtifactRenderer understands. */
function toParsedArtifactType(artifactType: string): ArtifactType {
  if (FRONTEND_ARTIFACT_TYPES.has(artifactType as ArtifactType)) {
    return artifactType as ArtifactType;
  }
  // "image", "text", "web-preview", and any other backend-only type fall back
  // to ArtifactRenderer's default case (plain text/pre rendering).
  return 'document';
}

function toParsedArtifact(doc: ArtifactDoc): ParsedArtifact {
  return {
    id: doc.name,
    type: toParsedArtifactType(doc.artifact_type),
    title: doc.title,
    language: doc.language,
    content: doc.content,
  };
}

export function ArtifactViewPage() {
  const { artifactId } = useParams<{ artifactId: string }>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [artifact, setArtifact] = useState<ArtifactDoc | null>(null);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const [showPdfPreview, setShowPdfPreview] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!artifactId) {
      setError('No artifact ID provided');
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function loadArtifact() {
      try {
        const doc = await getArtifact(artifactId!);
        if (!cancelled) {
          setArtifact(doc);
        }
      } catch (err) {
        console.error('Error fetching artifact:', err);
        if (!cancelled) {
          setError('Failed to load artifact. It may not exist or you may not have access.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadArtifact();

    return () => {
      cancelled = true;
    };
  }, [artifactId]);

  // Loading state
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-paper">
        <div className="flex flex-col items-center gap-3 text-steel">
          <Loader2 className="size-8 animate-spin" />
          <p className="text-sm">Loading artifact...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error || !artifact) {
    return (
      <div className="flex h-screen items-center justify-center bg-paper">
        <div className="flex max-w-md flex-col items-center gap-4 text-center">
          <AlertCircle className="size-10 text-steel-soft" />
          <div>
            <p className="font-medium text-foreground">
              {error || 'Failed to load artifact. It may not exist or you may not have access.'}
            </p>
            <p className="mt-1 text-sm text-steel">
              Artifact ID: {artifactId}
            </p>
          </div>
          {artifact?.conversation ? (
            <Link to={`/chat/${artifact.conversation}`}>
              <Button variant="outline" size="sm">
                <ArrowLeft className="mr-2 size-4" />
                Back to chat
              </Button>
            </Link>
          ) : (
            <Link to="/chat">
              <Button variant="outline" size="sm">
                <ArrowLeft className="mr-2 size-4" />
                Back
              </Button>
            </Link>
          )}
        </div>
      </div>
    );
  }

  const parsedArtifact = toParsedArtifact(artifact);

  return (
    <div className="flex h-screen flex-col bg-paper">
      {/* Toolbar */}
      <header className="flex shrink-0 items-center justify-between border-b px-4 py-2">
        <div className="flex items-center gap-3">
          <Link to={`/chat/${artifact.conversation}`}>
            <Button variant="ghost" size="sm">
              <ArrowLeft className="mr-2 size-4" />
              Back to chat
            </Button>
          </Link>
        </div>
        <div className="flex items-center gap-2">
          {artifact.message && (
            <Link to={`/view/${artifact.message}`}>
              <Button variant="outline" size="sm">
                Full message
              </Button>
            </Link>
          )}
          <ArtifactExportStandalone
            containerRef={containerRef}
            artifact={artifact}
            pdfPreviewUrl={pdfPreviewUrl}
            showPdfPreview={showPdfPreview}
            onPdfPreviewUrlChange={setPdfPreviewUrl}
            onShowPdfPreviewChange={setShowPdfPreview}
          />
        </div>
      </header>

      {/* Content */}
      <main className="min-h-0 flex-1 overflow-auto p-6">
        <div className="mx-auto max-w-4xl space-y-4">
          {/* PDF Preview */}
          {showPdfPreview && pdfPreviewUrl && (
            <div className="rounded border bg-panel">
              <iframe
                src={pdfPreviewUrl}
                className="w-full border-0 rounded"
                style={{ height: '600px' }}
                title="PDF preview"
              />
            </div>
          )}
          {/* Artifact Renderer */}
          <div ref={containerRef}>
            <ArtifactRenderer artifact={parsedArtifact} />
          </div>
        </div>
      </main>
    </div>
  );
}

/**
 * Standalone export button for the toolbar.
 * Handles PNG export and document/markdown download/preview (PDF, DOCX).
 */
function ArtifactExportStandalone({
  containerRef,
  artifact,
  pdfPreviewUrl,
  showPdfPreview,
  onPdfPreviewUrlChange,
  onShowPdfPreviewChange,
}: {
  containerRef: React.RefObject<HTMLDivElement | null>;
  artifact: ArtifactDoc;
  pdfPreviewUrl: string | null;
  showPdfPreview: boolean;
  onPdfPreviewUrlChange: (url: string | null) => void;
  onShowPdfPreviewChange: (show: boolean) => void;
}) {
  const [isExportingPng, setIsExportingPng] = useState(false);
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [isExportingDocx, setIsExportingDocx] = useState(false);

  const isDocumentType =
    artifact.artifact_type === 'document' || artifact.artifact_type === 'markdown';

  const handleExportPng = async () => {
    if (!containerRef.current) return;
    setIsExportingPng(true);
    try {
      const { toPng } = await import('html-to-image');
      const dataUrl = await toPng(containerRef.current, {
        backgroundColor: 'var(--panel)',
        pixelRatio: 2,
      });
      const link = document.createElement('a');
      link.download = 'artifact.png';
      link.href = dataUrl;
      link.click();
    } catch (err) {
      console.error('Failed to export PNG:', err);
    } finally {
      setIsExportingPng(false);
    }
  };

  const handleDownloadPdf = async () => {
    setIsExportingPdf(true);
    try {
      const result = await exportArtifact(artifact.name, 'pdf');
      if (result?.file_url) {
        window.open(result.file_url, '_blank');
      }
    } catch (err) {
      console.error('Failed to export PDF:', err);
    } finally {
      setIsExportingPdf(false);
    }
  };

  const handleDownloadDocx = async () => {
    setIsExportingDocx(true);
    try {
      const result = await exportArtifact(artifact.name, 'docx');
      if (result?.file_url) {
        window.open(result.file_url, '_blank');
      }
    } catch (err) {
      console.error('Failed to export DOCX:', err);
    } finally {
      setIsExportingDocx(false);
    }
  };

  const handleTogglePdfPreview = async () => {
    if (!showPdfPreview) {
      // Loading PDF preview
      if (!pdfPreviewUrl) {
        try {
          const result = await exportArtifact(artifact.name, 'pdf');
          if (result?.file_url) {
            onPdfPreviewUrlChange(result.file_url);
          }
        } catch (err) {
          console.error('Failed to load PDF preview:', err);
          return;
        }
      }
    }
    onShowPdfPreviewChange(!showPdfPreview);
  };

  return (
    <div className="flex items-center gap-2">
      {isDocumentType && (
        <>
          <Button
            variant="outline"
            size="sm"
            onClick={handleDownloadPdf}
            disabled={isExportingPdf}
          >
            <FileText className="mr-2 size-4" />
            {isExportingPdf ? 'Exporting...' : 'PDF'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleDownloadDocx}
            disabled={isExportingDocx}
          >
            <FileText className="mr-2 size-4" />
            {isExportingDocx ? 'Exporting...' : 'DOCX'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleTogglePdfPreview}
            disabled={isExportingPdf}
          >
            {showPdfPreview ? (
              <>
                <EyeOff className="mr-2 size-4" />
                Hide PDF
              </>
            ) : (
              <>
                <Eye className="mr-2 size-4" />
                Preview PDF
              </>
            )}
          </Button>
        </>
      )}
      <Button variant="outline" size="sm" onClick={handleExportPng} disabled={isExportingPng}>
        <ExternalLink className="mr-2 size-4" />
        {isExportingPng ? 'Exporting...' : 'Export PNG'}
      </Button>
    </div>
  );
}

export default ArtifactViewPage;
