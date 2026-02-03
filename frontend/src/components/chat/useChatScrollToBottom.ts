import { useCallback, useEffect, useRef } from 'react';

import type { MessageType } from './types';

export function useChatScrollToBottom(args: {
  chatId: string | null;
  initialLoading: boolean;
  messages: MessageType[];
}) {
  const { chatId, initialLoading, messages } = args;

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const lastMessageKeyRef = useRef<string | null>(null);
  const didInitialScrollKeyRef = useRef<string | null>(null);

  const scrollToBottom = useCallback((instant = false) => {
    const el = scrollContainerRef.current;
    if (!el) return;

    el.scrollTo({
      top: el.scrollHeight,
      behavior: instant ? 'auto' : 'smooth',
    });
  }, []);

  const scrollToBottomAfterPaint = useCallback(
    (instant = false) => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          scrollToBottom(instant);
        });
      });
    },
    [scrollToBottom]
  );

  // Initial load / chat switch: jump to bottom and set the last key baseline
  useEffect(() => {
    if (initialLoading || messages.length === 0) return;

    const scrollKey = chatId ?? '__new_chat__';
    if (didInitialScrollKeyRef.current === scrollKey) return;

    scrollToBottomAfterPaint(true);
    lastMessageKeyRef.current = messages[messages.length - 1]?.key ?? null;
    didInitialScrollKeyRef.current = scrollKey;
  }, [initialLoading, chatId, messages.length, scrollToBottomAfterPaint]);

  // New message appended: smooth scroll
  useEffect(() => {
    if (initialLoading || messages.length === 0) return;

    const currentLastKey = messages[messages.length - 1]?.key ?? null;
    if (currentLastKey !== lastMessageKeyRef.current) {
      scrollToBottomAfterPaint(false);
    }

    lastMessageKeyRef.current = currentLastKey;
  }, [messages, initialLoading, scrollToBottomAfterPaint]);

  return { scrollContainerRef, scrollToBottomAfterPaint };
}

