import { useCallback, useEffect, useState } from 'react';
import { listConversationArtifacts, type ArtifactListItem } from '@/services/artifactPanelApi';

export interface UseConversationArtifactsResult {
  artifacts: ArtifactListItem[];
  loading: boolean;
  /** Re-fetch the list on demand, e.g. after a socket event references an
   * artifact_id not yet in the last-fetched list (see `show_artifact`
   * handling in ChatPageV2). */
  refetch: () => Promise<ArtifactListItem[]>;
}

/**
 * Fetches the artifact list for a conversation once and shares it between
 * consumers that both need it — `ArtifactsPanel` (the list rail) and
 * `ArtifactPreviewPane`'s header quick-switcher (see PLAN_PANE_UX.md
 * item 3). Lifted out of `ArtifactsPanel` so opening the preview pane
 * (which hides the list rail) doesn't lose access to the same data, and so
 * neither consumer double-fetches.
 */
export function useConversationArtifacts(
  conversationId: string | undefined
): UseConversationArtifactsResult {
  const [artifacts, setArtifacts] = useState<ArtifactListItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!conversationId) {
      setArtifacts([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    listConversationArtifacts(conversationId).then((items) => {
      if (!cancelled) {
        setArtifacts(items);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const refetch = useCallback(async () => {
    if (!conversationId) {
      return [];
    }
    const items = await listConversationArtifacts(conversationId);
    setArtifacts(items);
    return items;
  }, [conversationId]);

  return { artifacts, loading, refetch };
}
