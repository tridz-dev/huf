/**
 * ArtifactPreviewPane — right-docked pane that previews a durable document
 * artifact in place, instead of opening `/artifact/:name` in a new tab.
 *
 * This is intentionally a thin host: document rendering is delegated to
 * `DocumentPreview` (frontend/src/components/chat/DocumentPreview.tsx), which
 * already knows how to fetch and sandbox-render a saved Artifact's HTML by
 * name. This component owns the pane chrome (header, title, close button,
 * quick-switcher dropdown) and layout, plus the drag-to-resize handle on its
 * left edge.
 *
 * Visual cues and the resize mechanism are borrowed from `RightSidebar.tsx`
 * (border-l, bg-card, header + scrollable body; mouse-move drag-resize
 * pattern around RightSidebar.tsx:49,64-82) without depending on it — that
 * component is Flow Canvas-specific and unrelated to chat.
 */
import { useCallback, useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { DocumentPreview } from '@/components/chat/DocumentPreview';
import { isDocumentType } from '@/components/chat/ArtifactsPanel';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { ArtifactPaneTarget } from '@/components/chat/useArtifactPane';
import type { ArtifactListItem } from '@/services/artifactPanelApi';

export interface ArtifactPreviewPaneProps {
  /** Artifact to preview, or null when the pane should be hidden. */
  artifact: ArtifactPaneTarget | null;
  onClose: () => void;
  /** Current pane width in px, owned by `useArtifactPane`. */
  width: number;
  onWidthChange: (px: number) => void;
  /**
   * All artifacts in the conversation (shared with `ArtifactsPanel` via
   * `useConversationArtifacts` — see ChatPageV2.tsx). Filtered here to
   * document/markdown types for the quick-switcher, since those are the
   * only types this pane can render.
   */
  artifacts: ArtifactListItem[];
  onSelectArtifact: (artifact: ArtifactPaneTarget) => void;
}

export function ArtifactPreviewPane({
  artifact,
  onClose,
  width,
  onWidthChange,
  artifacts,
  onSelectArtifact,
}: ArtifactPreviewPaneProps) {
  const [isResizing, setIsResizing] = useState(false);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  useEffect(() => {
    if (!isResizing) return;
    const handleMouseMove = (e: MouseEvent) => {
      // Handle is on the pane's left edge, so width grows as the pointer
      // moves left (mirrors RightSidebar.tsx's `window.innerWidth - e.clientX`).
      onWidthChange(window.innerWidth - e.clientX);
    };
    const handleMouseUp = () => setIsResizing(false);
    // Without this, dragging the handle sweeps a text selection across the
    // chat transcript and the document preview underneath it.
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.body.style.userSelect = previousUserSelect;
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing, onWidthChange]);

  if (!artifact) {
    return null;
  }

  const documentArtifacts = artifacts.filter((a) => isDocumentType(a.artifact_type));

  return (
    <div
      className="relative flex h-full shrink-0 flex-col border-l border-line bg-paper"
      style={{ width }}
    >
      <div
        className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/50 transition-colors"
        onMouseDown={handleMouseDown}
      />

      <div className="flex h-chat-header flex-none items-center gap-2.5 border-b border-line px-3.5">
        {documentArtifacts.length > 1 ? (
          <Select
            value={artifact.name}
            onValueChange={(name) => {
              const next = documentArtifacts.find((a) => a.name === name);
              if (next) {
                onSelectArtifact({
                  name: next.name,
                  title: next.title,
                  artifact_type: next.artifact_type,
                });
              }
            }}
          >
            <SelectTrigger className="h-auto min-w-0 flex-none max-w-[60%] border-none bg-transparent p-0 text-[13px] font-medium shadow-none focus:ring-0">
              <SelectValue placeholder="Document preview">
                <span className="truncate">{artifact.title || 'Document preview'}</span>
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {documentArtifacts.map((a) => (
                <SelectItem key={a.name} value={a.name}>
                  {a.title || a.artifact_type}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <h2 className="min-w-0 flex-none max-w-[60%] truncate text-[13px] font-medium">
            {artifact.title || 'Document preview'}
          </h2>
        )}
        <span className="font-mono text-[11px] uppercase text-steel-soft">
          {artifact.artifact_type}
        </span>
        <span className="flex-1" />
        <button
          type="button"
          onClick={onClose}
          aria-label="Close preview"
          className="text-steel hover:text-ink"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <DocumentPreview artifactName={artifact.name} />
      </div>
    </div>
  );
}

export default ArtifactPreviewPane;
