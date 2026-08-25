import { useCallback, useState } from 'react';

export interface UseConversationAnalyticsPaneResult {
  isOpen: boolean;
  open: () => void;
  close: () => void;
}

/**
 * State for the right-docked conversation analytics pane. Modelled on
 * `useArtifactPane` (see useArtifactPane.ts), but deliberately smaller:
 * there is no "current target" to track — the pane always shows analytics
 * for whichever conversation is open — and no width state of its own,
 * because the analytics pane shares the same right-pane slot (and its
 * persisted width) with the artifact preview pane. The slot's width is
 * owned by `useArtifactPane`; callers pass it through to
 * `ConversationAnalyticsPane` so both tabs agree on one size.
 */
export function useConversationAnalyticsPane(): UseConversationAnalyticsPaneResult {
  const [isOpen, setIsOpen] = useState(false);

  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);

  return { isOpen, open, close };
}
