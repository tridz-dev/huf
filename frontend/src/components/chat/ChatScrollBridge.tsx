import { useEffect, useLayoutEffect } from 'react';
import type { MutableRefObject } from 'react';
import { useStickToBottomContext } from 'use-stick-to-bottom';
import type { ScrollToBottom } from 'use-stick-to-bottom';

interface ChatScrollBridgeProps {
  infiniteScrollRef: MutableRefObject<HTMLElement | null>;
  onScrollToBottomReady: (scrollToBottom: ScrollToBottom) => void;
}

/**
 * Syncs the infinite-scroll observer ref with StickToBottom's scroll container
 * and exposes scrollToBottom to sibling components (e.g. ChatInput).
 */
export function ChatScrollBridge({
  infiniteScrollRef,
  onScrollToBottomReady,
}: ChatScrollBridgeProps) {
  const { scrollRef, scrollToBottom } = useStickToBottomContext();

  useLayoutEffect(() => {
    infiniteScrollRef.current = scrollRef.current;
  });

  useEffect(() => {
    onScrollToBottomReady(scrollToBottom);
  }, [onScrollToBottomReady, scrollToBottom]);

  return null;
}
