import { useEffect, useRef } from 'react';
import { getConversation } from '@/services/chatApi';
import { isDefaultConversationTitle } from '@/utils/conversationTitle';

export const TITLE_FALLBACK_GRACE_MS = 3000;
export const TITLE_FALLBACK_INTERVAL_MS = 5000;
export const TITLE_FALLBACK_MAX_RETRIES = 3;

export const TITLE_POST_SUCCESS_GRACE_MS = 4000;
export const TITLE_POST_SUCCESS_INTERVAL_MS = 5000;
export const TITLE_POST_SUCCESS_MAX_RETRIES = 2;

export type ConversationTitleUpdatedDetail = {
  conversationId: string;
  title: string;
  animate?: boolean;
};

export function dispatchConversationTitleUpdated(detail: ConversationTitleUpdatedDetail) {
  window.dispatchEvent(
    new CustomEvent<ConversationTitleUpdatedDetail>('huf:conversation-title-updated', {
      detail,
    })
  );
}

type UseConversationTitleSwitchFallbackOptions = {
  conversationId: string | null;
  currentTitle: string | null | undefined;
  autonamingEnabled: boolean;
  enabled?: boolean;
};

/**
 * Polls for an auto-named title when the user switches to a conversation
 * that still has a default title (socket event may have been missed).
 */
export function useConversationTitleSwitchFallback({
  conversationId,
  currentTitle,
  autonamingEnabled,
  enabled = true,
}: UseConversationTitleSwitchFallbackOptions) {
  const inFlightRef = useRef(false);
  const retriesRef = useRef(0);

  useEffect(() => {
    if (!enabled || !conversationId || !autonamingEnabled) {
      return;
    }
    if (!currentTitle || !isDefaultConversationTitle(currentTitle)) {
      return;
    }

    retriesRef.current = 0;
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | undefined;

    const fetchTitle = async () => {
      if (cancelled || inFlightRef.current) return;
      inFlightRef.current = true;
      try {
        const conversation = await getConversation(conversationId);
        if (cancelled || !conversation?.title) return;

        if (!isDefaultConversationTitle(conversation.title)) {
          dispatchConversationTitleUpdated({
            conversationId,
            title: conversation.title,
            animate: true,
          });
          if (intervalId) {
            clearInterval(intervalId);
            intervalId = undefined;
          }
        }
      } catch {
        // Non-critical — next tick retries
      } finally {
        inFlightRef.current = false;
      }
    };

    const graceTimeoutId = setTimeout(() => {
      if (cancelled) return;
      void fetchTitle();
      intervalId = setInterval(() => {
        retriesRef.current += 1;
        if (retriesRef.current > TITLE_FALLBACK_MAX_RETRIES) {
          if (intervalId) clearInterval(intervalId);
          return;
        }
        void fetchTitle();
      }, TITLE_FALLBACK_INTERVAL_MS);
    }, TITLE_FALLBACK_GRACE_MS);

    return () => {
      cancelled = true;
      clearTimeout(graceTimeoutId);
      if (intervalId) clearInterval(intervalId);
    };
  }, [conversationId, currentTitle, autonamingEnabled, enabled]);
}

type UseConversationTitlePostSuccessFallbackOptions = {
  conversationId: string | null;
  currentTitle: string | null | undefined;
  autonamingEnabled: boolean;
  runSucceeded: boolean;
};

/**
 * After a successful agent run, poll once for an auto-named title if the
 * sidebar still shows a default title (background job may lag the socket).
 */
export function useConversationTitlePostSuccessFallback({
  conversationId,
  currentTitle,
  autonamingEnabled,
  runSucceeded,
}: UseConversationTitlePostSuccessFallbackOptions) {
  const inFlightRef = useRef(false);
  const retriesRef = useRef(0);

  useEffect(() => {
    if (!runSucceeded || !conversationId || !autonamingEnabled) {
      return;
    }
    if (!currentTitle || !isDefaultConversationTitle(currentTitle)) {
      return;
    }

    retriesRef.current = 0;
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | undefined;

    const fetchTitle = async () => {
      if (cancelled || inFlightRef.current) return;
      inFlightRef.current = true;
      try {
        const conversation = await getConversation(conversationId);
        if (cancelled || !conversation?.title) return;

        if (!isDefaultConversationTitle(conversation.title)) {
          dispatchConversationTitleUpdated({
            conversationId,
            title: conversation.title,
            animate: true,
          });
          if (intervalId) {
            clearInterval(intervalId);
            intervalId = undefined;
          }
        }
      } catch {
        // Non-critical
      } finally {
        inFlightRef.current = false;
      }
    };

    const graceTimeoutId = setTimeout(() => {
      if (cancelled) return;
      void fetchTitle();
      intervalId = setInterval(() => {
        retriesRef.current += 1;
        if (retriesRef.current > TITLE_POST_SUCCESS_MAX_RETRIES) {
          if (intervalId) clearInterval(intervalId);
          return;
        }
        void fetchTitle();
      }, TITLE_POST_SUCCESS_INTERVAL_MS);
    }, TITLE_POST_SUCCESS_GRACE_MS);

    return () => {
      cancelled = true;
      clearTimeout(graceTimeoutId);
      if (intervalId) clearInterval(intervalId);
    };
  }, [runSucceeded, conversationId, currentTitle, autonamingEnabled]);
}
