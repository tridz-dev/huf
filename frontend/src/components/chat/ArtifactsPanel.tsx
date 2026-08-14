import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import {
  BarChart3,
  Code2,
  Download,
  FileText,
  Image as ImageIcon,
  Network,
  PanelRightClose,
  PanelRightOpen,
  Video,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatTimeAgo } from '@/utils/time';
import { exportArtifactFromPanel, type ArtifactListItem } from '@/services/artifactPanelApi';
import type { ArtifactPaneTarget } from '@/components/chat/useArtifactPane';

const COLLAPSED_STORAGE_KEY = 'huf-artifacts-panel-collapsed';

// Mirrors the `artifact_type` Select options on the Artifact doctype:
// code, document, markdown, html, svg, mermaid, chart, jsx, video, image,
// web-preview, text.
const ARTIFACT_TYPE_ICONS: Record<string, LucideIcon> = {
  code: Code2,
  jsx: Code2,
  html: Code2,
  'web-preview': Code2,
  svg: ImageIcon,
  image: ImageIcon,
  video: Video,
  chart: BarChart3,
  mermaid: Network,
  document: FileText,
  markdown: FileText,
  text: FileText,
};

function getArtifactIcon(artifactType: string): LucideIcon {
  return ARTIFACT_TYPE_ICONS[artifactType] ?? FileText;
}

export function isDocumentType(artifactType: string): boolean {
  return artifactType === 'document' || artifactType === 'markdown';
}

function readCollapsedPreference(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(COLLAPSED_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

export interface ArtifactsPanelProps {
  /** Artifacts to list, fetched once by the shared `useConversationArtifacts` hook in ChatPageV2 and passed down here (and to `ArtifactPreviewPane`'s header switcher) so neither consumer double-fetches. */
  artifacts: ArtifactListItem[];
  loading: boolean;
  /**
   * When provided, clicking a document/markdown artifact opens it in the
   * in-app preview pane (see ArtifactPreviewPane.tsx) instead of navigating
   * to `/artifact/:name` in a new tab. Other artifact types (code, chart,
   * etc.) keep the existing new-tab behavior regardless, since only
   * DocumentPreview-backed types are supported by the pane today.
   */
  onOpenArtifact?: (artifact: ArtifactPaneTarget) => void;
}

export function ArtifactsPanel({ artifacts, loading, onOpenArtifact }: ArtifactsPanelProps) {
  const [collapsed, setCollapsed] = useState<boolean>(readCollapsedPreference);
  const [exporting, setExporting] = useState<Record<string, boolean>>({});

  useEffect(() => {
    try {
      window.localStorage.setItem(COLLAPSED_STORAGE_KEY, collapsed ? '1' : '0');
    } catch {
      // localStorage unavailable (private mode, etc.) - preference just won't persist.
    }
  }, [collapsed]);

  const handleExport = async (
    artifactName: string,
    format: 'pdf' | 'docx',
    e: React.MouseEvent
  ) => {
    e.preventDefault();
    e.stopPropagation();

    const key = `${artifactName}-${format}`;
    setExporting((prev) => ({ ...prev, [key]: true }));

    const result = await exportArtifactFromPanel(artifactName, format);
    setExporting((prev) => ({ ...prev, [key]: false }));

    if (result?.file_url) {
      window.open(result.file_url, '_blank');
    }
  };

  const count = artifacts.length;

  if (collapsed) {
    return (
      <Button
        type="button"
        variant="ghost"
        onClick={() => setCollapsed(false)}
        aria-label="Expand artifacts panel"
        className="relative h-auto w-10 shrink-0 flex-col items-center gap-2 rounded-none border-l border-line bg-panel py-4 text-muted-foreground hover:bg-muted/40 hover:text-foreground"
      >
        <PanelRightOpen className="size-4" />
        <span className="rotate-180 text-xs font-medium tracking-wide [writing-mode:vertical-rl]">
          Artifacts
        </span>
        {count > 0 && (
          <span className="flex size-5 items-center justify-center rounded-full bg-primary text-[10px] font-medium text-primary-foreground">
            {count}
          </span>
        )}
      </Button>
    );
  }

  return (
    <div className="flex h-full w-80 shrink-0 flex-col border-l border-line bg-panel">
      <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">Artifacts</h2>
          {count > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-muted px-1.5 text-[11px] font-medium text-muted-foreground">
              {count}
            </span>
          )}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={() => setCollapsed(true)}
          aria-label="Collapse artifacts panel"
          className="h-auto w-auto rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <PanelRightClose className="size-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && artifacts.length === 0 ? (
          <p className="px-3 py-4 text-sm text-muted-foreground">Loading...</p>
        ) : count === 0 ? (
          <p className="px-3 py-4 text-sm text-muted-foreground">No artifacts yet</p>
        ) : (
          <ul className="flex flex-col divide-y divide-line">
            {artifacts.map((artifact) => {
              const Icon = getArtifactIcon(artifact.artifact_type);
              const isDoc = isDocumentType(artifact.artifact_type);
              const pdfKey = `${artifact.name}-pdf`;
              const isPdfExporting = exporting[pdfKey];
              const rowContent = (
                <>
                  <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {artifact.title || artifact.artifact_type}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {isDoc && (
                        <>
                          <span className="inline-block mr-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-muted text-muted-foreground">
                            DOC
                          </span>
                        </>
                      )}
                      {artifact.artifact_type}
                      {' · '}
                      {formatTimeAgo(artifact.creation)}
                    </p>
                  </div>
                </>
              );
              return (
                <li key={artifact.name}>
                  <div className="flex items-start gap-2 px-3 py-2.5 hover:bg-muted/40 group">
                    {isDoc && onOpenArtifact ? (
                      <button
                        type="button"
                        onClick={() =>
                          onOpenArtifact({
                            name: artifact.name,
                            title: artifact.title,
                            artifact_type: artifact.artifact_type,
                          })
                        }
                        className="flex items-start gap-2 min-w-0 flex-1 text-left"
                      >
                        {rowContent}
                      </button>
                    ) : (
                      <Link
                        to={`/artifact/${artifact.name}`}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-start gap-2 min-w-0 flex-1"
                      >
                        {rowContent}
                      </Link>
                    )}
                    {isDoc && (
                      <div className="flex gap-1 shrink-0 ml-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          onClick={(e) => handleExport(artifact.name, 'pdf', e)}
                          disabled={isPdfExporting}
                          aria-label="Download as PDF"
                          className="h-auto w-auto rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                          title="Download as PDF"
                        >
                          <Download className="size-4" />
                        </Button>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

export default ArtifactsPanel;
