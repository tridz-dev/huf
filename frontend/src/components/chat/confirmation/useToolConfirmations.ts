import { useCallback, useEffect, useRef, useState } from 'react';
import { getConversationMessages, type ChatMessage } from '@/services/chatApi';
import type { ApprovalEvent } from '@/hooks/useChatSocket';
import { getPendingConfirmations, normalize as normalizeConfirmation, type ToolConfirmation } from '@/services/toolConfirmation/toolConfirmationApi';

export function useToolConfirmations(chatId: string | undefined, appendConversationItems: (items: ChatMessage[]) => void) {
  // N06 confirm-before-send: latest known state per confirmation id.
  const [confirmations, setConfirmations] = useState<Record<string, ToolConfirmation>>({});
  const upsertConfirmation = useCallback((c: ToolConfirmation) => {
      setConfirmations((prev) => ({ ...prev, [c.id]: c }));
  }, []);

  const handleApproval = useCallback((event: ApprovalEvent) => {
      if (event.conversation_id && event.conversation_id !== chatId) return;
      if (event.confirmation && typeof event.confirmation === 'object') {
          upsertConfirmation(normalizeConfirmation(event.confirmation));
      }
      if (event.type === 'approval-resolved') void refreshHistoryRef.current();
  }, [chatId, upsertConfirmation]);
  const refreshHistoryRef = useRef<() => Promise<void>>(async () => {});

  // Events are best-effort: load pending approvals on open.
  useEffect(() => {
      setConfirmations({});
      if (!chatId) return;
      let cancelled = false;
      getPendingConfirmations(chatId)
          .then((list) => {
              if (cancelled) return;
              setConfirmations((prev) => {
                  const next = { ...prev };
                  list.forEach((c) => { if (!next[c.id]) next[c.id] = c; });
                  return next;
              });
          })
          .catch(() => { /* non-fatal: history + realtime still render cards */ });
      return () => { cancelled = true; };
  }, [chatId]);

  // After a decision (or an approval-resolved event), pull the follow-up
  // (confirmation_result) message from history into the infinite-scroll
  // source list so it survives re-merges (never a local-only append).
  const refreshHistory = useCallback(async (): Promise<ChatMessage[]> => {
      if (!chatId) return [];
      try {
          const latest = await getConversationMessages({ conversation: chatId, limit: 10, start: 0 });
          appendConversationItems(latest.data);
          return latest.data;
      } catch { return []; /* the card already shows the decided state */ }
  }, [chatId, appendConversationItems]);
  const handleConfirmationDecided = useCallback(async (c?: ToolConfirmation) => {
      const first = await refreshHistory();
      if (!c || c.state !== 'approved') return;
      // Async execution: poll get_pending + history until executed|failed (max ~2 min).
      const terminal = (items: ChatMessage[]): ToolConfirmation | null => {
          for (const it of items) {
              const m = typeof it.content === 'string' ? it.content : '';
              if (!m.includes('confirmation_result') || !m.includes(c.id)) continue;
              try {
                  const o = JSON.parse(m);
                  if (o?.id === c.id && (o.state === 'executed' || o.state === 'failed')) return { ...c, state: o.state };
              } catch { /* ignore */ }
          }
          return null;
      };
      let done = terminal(first);
      for (let i = 0; i < 40 && !done; i++) {
          await new Promise((r) => setTimeout(r, 3000));
          try {
              const pend = (await getPendingConfirmations(chatId)).find((p) => p.id === c.id);
              if (pend && (pend.state === 'executed' || pend.state === 'failed')) done = pend;
          } catch { /* keep polling */ }
          if (!done) done = terminal(await refreshHistory());
      }
      if (done) upsertConfirmation(done);
  }, [chatId, refreshHistory, upsertConfirmation]);

  refreshHistoryRef.current = async () => { await refreshHistory(); };

  return { confirmations, upsertConfirmation, handleApproval, handleConfirmationDecided };
}
