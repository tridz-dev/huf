// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import type { ChatMessage } from '@/services/chatApi';
import type { MessageType } from '../types';

const getDocList = vi.fn();
vi.mock('@/lib/frappe-sdk', () => ({ db: { getDocList: (...a: unknown[]) => getDocList(...a) } }));

import { useCancelledRuns, withCancelledRuns, type CancelledRun } from './cancelledRuns';

const msg = (key: string, from: 'user' | 'assistant', content: string, agentRunId?: string): MessageType => ({
  key,
  from,
  agentRunId,
  versions: [{ id: key, content }],
});
const item = (id: string, createdAt: string): ChatMessage => ({ id, conversation: 'c', content: '', isAgent: false, createdAt });
const run = (name: string, prompt: string, second: number): CancelledRun => ({
  name,
  prompt,
  creation: `2026-01-01 10:00:${String(second).padStart(2, '0')}.000000`,
});
const view = (messages: MessageType[]) => messages.map((m) => `${m.from}:${m.error ?? m.versions[0].content}`);

describe('withCancelledRuns', () => {
  it('keeps the partial reply of a stopped stream and adds the marker once', () => {
    const loaded = [msg('m1', 'user', 'hi', 'r1'), msg('m2', 'assistant', 'partial', 'r1')];
    const out = withCancelledRuns(loaded, [run('r1', 'hi', 1)], [], false);
    expect(view(out)).toEqual(['user:hi', 'assistant:partial', 'assistant:Cancelled by user']);
    expect(withCancelledRuns(out, [run('r1', 'hi', 1)], [], false)).toEqual(out);
  });

  it('marks a stopped started run that only saved the user message', () => {
    const out = withCancelledRuns([msg('m1', 'user', 'go', 'r1')], [run('r1', 'go', 1)], [], false);
    expect(view(out)).toEqual(['user:go', 'assistant:Cancelled by user']);
  });

  it('restores the user messages of cancelled queued runs, in order', () => {
    const out = withCancelledRuns([], [run('r2', 'second', 2), run('r1', 'first', 1)], [], false);
    expect(view(out)).toEqual(['user:first', 'assistant:Cancelled by user', 'user:second', 'assistant:Cancelled by user']);
  });

  it('places a cancelled turn before later turns, even with a repeated prompt', () => {
    const loaded = [msg('m1', 'user', 'hi', 'r0'), msg('m3', 'user', 'later', 'r9')];
    const items = [item('m1', '2026-01-01 10:00:00.000000'), item('m3', '2026-01-01 10:00:30.000000')];
    const out = withCancelledRuns(loaded, [run('r1', 'hi', 5)], items, false);
    expect(view(out)).toEqual(['user:hi', 'user:hi', 'assistant:Cancelled by user', 'user:later']);
  });

  it('does not duplicate an unlinked saved or live user message', () => {
    const saved = withCancelledRuns([msg('m1', 'user', 'read this')], [run('r1', 'read this\n[file text]', 3)], [item('m1', '2026-01-01 10:00:02.000000')], false);
    expect(view(saved)).toEqual(['user:read this', 'assistant:Cancelled by user']);
    const live = withCancelledRuns([msg('user-1', 'user', 'hi')], [run('r1', 'hi', 3)], [], false);
    expect(view(live)).toEqual(['user:hi', 'assistant:Cancelled by user']);
  });

  it('leaves runs older than the loaded page for that page', () => {
    const items = [item('m9', '2026-01-01 10:00:30.000000')];
    expect(withCancelledRuns([msg('m9', 'user', 'new', 'r9')], [run('r1', 'old', 1)], items, true)).toHaveLength(1);
  });
});

describe('useCancelledRuns', () => {
  it('loads the stopped runs of a reloaded conversation', async () => {
    getDocList.mockResolvedValue([run('r1', 'hello', 1)]);
    const items: ChatMessage[] = [];
    const messages: MessageType[] = [];
    const { result } = renderHook(() => useCancelledRuns('c', items, messages, false));
    await waitFor(() => expect(view(result.current)).toEqual(['user:hello', 'assistant:Cancelled by user']));
    expect(getDocList.mock.calls[0][1].filters).toContainEqual(['error_message', '=', 'Cancelled by user']);
  });
});
