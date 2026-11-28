import { useEffect, useMemo, useState } from 'react';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { ChatMessage } from '@/services/chatApi';
import type { MessageType } from '../types';
import { CANCELLED_BY_USER } from './runControl';

/** An Agent Run the user stopped. Its cancelled state lives only on the run itself. */
export interface CancelledRun {
  name: string;
  prompt?: string | null;
  creation: string;
}

/** A message saved just before its run (file, voice) is only matched this close to it. */
const UNLINKED_WINDOW_MS = 60_000;

export async function getCancelledConversationRuns(conversationId: string): Promise<CancelledRun[]> {
  return (await db.getDocList(doctype['Agent Run'], {
    fields: ['name', 'prompt', 'creation'],
    filters: [
      ['conversation', '=', conversationId],
      ['status', '=', 'Failed'],
      ['error_message', '=', CANCELLED_BY_USER],
      ['is_child', '=', 0],
    ],
    orderBy: { field: 'creation', order: 'desc' },
    limit: 50,
  })) as CancelledRun[];
}

const time = (value: string) => Date.parse(value.replace(' ', 'T'));

/** The user message of a run that was never linked to it, matched by its text. */
function findUnlinkedUser(messages: MessageType[], run: CancelledRun, created: Map<string, string>, used: Set<string>) {
  const prompt = run.prompt?.trim() ?? '';
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.from !== 'user' || message.agentRunId || used.has(message.key)) continue;
    const content = message.versions[0]?.content?.trim();
    if (!content) continue;
    const savedAt = created.get(message.key);
    const matches = savedAt
      ? prompt.includes(content) && Math.abs(time(savedAt) - time(run.creation)) <= UNLINKED_WINDOW_MS
      : prompt === content;
    if (matches) return i;
  }
  return -1;
}

/**
 * Rebuild the cancelled state from run records: a marker after whatever the run
 * left behind (partial reply, tool rows, user message), and the user message
 * itself when the run was stopped before it was ever saved. Idempotent.
 */
export function withCancelledRuns(
  messages: MessageType[],
  runs: CancelledRun[],
  items: ChatMessage[],
  hasMore: boolean
): MessageType[] {
  if (runs.length === 0) return messages;
  const created = new Map<string, string>();
  items.forEach((item) => {
    if (item.createdAt) created.set(item.id, item.createdAt);
  });
  const oldest = [...created.values()].sort()[0];
  const used = new Set<string>();
  const result = [...messages];

  for (const run of [...runs].sort((a, b) => a.creation.localeCompare(b.creation))) {
    if (run.prompt?.startsWith('[SILENT_TRIGGER]')) continue;
    const own = result.filter((m) => m.agentRunId === run.name || m.key === run.name);
    // A live bubble already shows (or is about to show) how the run ended.
    if (own.some((m) => m.from === 'assistant' && (m.error || m.stopping || m.runStatus === 'Queued' || m.runStatus === 'Started'))) {
      continue;
    }
    const marker: MessageType = {
      key: `cancelled-${run.name}`,
      from: 'assistant',
      agentRunId: run.name,
      runStatus: 'Failed',
      error: CANCELLED_BY_USER,
      versions: [{ id: `cancelled-${run.name}`, content: '' }],
    };
    if (own.length > 0) {
      result.splice(result.indexOf(own[own.length - 1]) + 1, 0, marker);
      continue;
    }
    const unlinked = findUnlinkedUser(result, run, created, used);
    if (unlinked >= 0) {
      used.add(result[unlinked].key);
      result.splice(unlinked + 1, 0, marker);
      continue;
    }
    // Older than the loaded page: its message arrives with an earlier page.
    if (hasMore && (!oldest || run.creation < oldest)) continue;
    const userKey = `cancelled-user-${run.name}`;
    const prompt = run.prompt?.trim();
    const turn: MessageType[] = prompt
      ? [{ key: userKey, from: 'user', agentRunId: run.name, versions: [{ id: userKey, content: prompt }] }, marker]
      : [marker];
    // Before the first later turn; unsaved bubbles (open runs) are always later.
    const at = result.findIndex((m) => {
      const savedAt = created.get(m.key);
      return savedAt ? m.from === 'user' && savedAt > run.creation : !m.key.startsWith('cancelled-');
    });
    turn.forEach((m) => created.set(m.key, run.creation));
    result.splice(at < 0 ? result.length : at, 0, ...turn);
  }

  return result;
}

/** Loaded messages with the cancelled state of stopped runs put back (survives reload). */
export function useCancelledRuns(
  chatId: string | null,
  items: ChatMessage[],
  messages: MessageType[],
  hasMore: boolean
): MessageType[] {
  const [loaded, setLoaded] = useState<{ chatId: string; runs: CancelledRun[] } | null>(null);

  useEffect(() => {
    if (!chatId) return;
    let stale = false;
    getCancelledConversationRuns(chatId)
      .then((runs) => {
        if (!stale) setLoaded({ chatId, runs });
      })
      .catch((error: unknown) => console.error('Error loading stopped runs:', error));
    return () => {
      stale = true;
    };
  }, [chatId, items]);

  return useMemo(
    () => (chatId && loaded?.chatId === chatId ? withCancelledRuns(messages, loaded.runs, items, hasMore) : messages),
    [chatId, loaded, messages, items, hasMore]
  );
}
