import { useCallback, useState } from 'react';

/**
 * Minimal identity needed to preview a durable document artifact in the
 * right-docked pane. Mirrors the subset of `ArtifactListItem`
 * (see artifactPanelApi.ts) that `DocumentPreview` and the pane header need —
 * kept separate so callers other than `ArtifactsPanel` (e.g. a future
 * artifact card in the message stream) can open the pane without importing
 * the panel's list-row type.
 */
export interface ArtifactPaneTarget {
  name: string;
  title?: string;
  artifact_type: string;
}

const WIDTH_STORAGE_KEY = 'huf-artifact-pane-width';
const DEFAULT_WIDTH_VW = 50;
const MIN_WIDTH_VW = 30;
const MAX_WIDTH_VW = 75;

function clampWidth(px: number): number {
  const min = (MIN_WIDTH_VW / 100) * window.innerWidth;
  const max = (MAX_WIDTH_VW / 100) * window.innerWidth;
  return Math.min(Math.max(px, min), max);
}

function readStoredWidth(): number {
  if (typeof window === 'undefined') {
    // No viewport to size against; the first client render re-reads this.
    return 0;
  }
  try {
    const raw = window.localStorage.getItem(WIDTH_STORAGE_KEY);
    const parsed = raw ? Number(raw) : NaN;
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return (DEFAULT_WIDTH_VW / 100) * window.innerWidth;
    }
    return clampWidth(parsed);
  } catch {
    return (DEFAULT_WIDTH_VW / 100) * window.innerWidth;
  }
}

export interface UseArtifactPaneResult {
  isOpen: boolean;
  currentArtifact: ArtifactPaneTarget | null;
  open: (artifact: ArtifactPaneTarget) => void;
  close: () => void;
  /** Pane width in pixels, clamped to [30vw, 75vw] and persisted to localStorage. */
  width: number;
  setWidth: (px: number) => void;
}

/**
 * State for the right-docked artifact preview pane. Plain `useState` is
 * enough here — there is exactly one pane per chat page, and its state
 * (which artifact, if any) needs no persistence across reloads, unlike
 * `ArtifactsPanel`'s collapsed/expanded preference (see
 * `COLLAPSED_STORAGE_KEY` in ArtifactsPanel.tsx) — except for `width`, which
 * follows that same storage-key convention so the chosen size survives
 * reload. Host components pass `open`/`close` down to whatever should
 * trigger the pane (currently `ArtifactsPanel`'s list rows).
 */
export function useArtifactPane(): UseArtifactPaneResult {
  const [currentArtifact, setCurrentArtifact] = useState<ArtifactPaneTarget | null>(null);
  const [width, setWidthState] = useState<number>(readStoredWidth);

  const open = useCallback((artifact: ArtifactPaneTarget) => {
    setCurrentArtifact(artifact);
  }, []);

  const close = useCallback(() => {
    setCurrentArtifact(null);
  }, []);

  const setWidth = useCallback((px: number) => {
    const clamped = clampWidth(px);
    setWidthState(clamped);
    try {
      window.localStorage.setItem(WIDTH_STORAGE_KEY, String(clamped));
    } catch {
      // localStorage unavailable (private mode, etc.) - preference just won't persist.
    }
  }, []);

  return {
    isOpen: currentArtifact !== null,
    currentArtifact,
    open,
    close,
    width,
    setWidth,
  };
}
