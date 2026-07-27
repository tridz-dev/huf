import { describe, it, expect } from 'vitest';
import {
  applyPolledRunStatus,
  mergeConversationItemsIntoMessages,
  mergePendingRunsIntoMessages,
  upsertAgentRunStatusFromSocket,
} from './chatMessageList.mappers';
import type { MessageType } from './types';
import type { ChatMessage, PendingConversationRun } from '@/services/chatApi';

/**
 * Regression tests for the queue-first lifecycle event contract.
 *
 * The backend emits `agent_run_status` events whose `status` must match the
 * Agent Run doctype spelling (Queued/Started/Success/Failed). The mapper must
 * also tolerate the legacy lowercase spelling, and must render the final
 * assistant text from the success event's `response` payload.
 */

function pendingRun(runId: string): MessageType {
  return {
    key: runId,
    from: 'assistant',
    runStatus: 'Queued',
    versions: [{ id: runId, content: '' }],
  };
}

describe('upsertAgentRunStatusFromSocket', () => {
  it('applies canonical capitalized statuses', () => {
    const prev: MessageType[] = [pendingRun('AR-1')];
    const next = upsertAgentRunStatusFromSocket(prev, {
      type: 'agent_run_status',
      agent_run_id: 'AR-1',
      conversation_id: 'CONV-1',
      status: 'Started',
    });
    expect(next[0].runStatus).toBe('Started');
  });

  it('tolerates legacy lowercase statuses', () => {
    const prev: MessageType[] = [pendingRun('AR-1')];
    const next = upsertAgentRunStatusFromSocket(prev, {
      type: 'agent_run_status',
      agent_run_id: 'AR-1',
      conversation_id: 'CONV-1',
      status: 'started',
    });
    expect(next[0].runStatus).toBe('Started');
  });

  it('renders the final text from a lowercase success event payload', () => {
    const prev: MessageType[] = [pendingRun('AR-1')];
    const next = upsertAgentRunStatusFromSocket(prev, {
      type: 'agent_run_status',
      agent_run_id: 'AR-1',
      conversation_id: 'CONV-1',
      status: 'success',
      response: 'the final answer',
      agent_message_id: 'AM-1',
    });
    expect(next[0].runStatus).toBe('Success');
    expect(next[0].versions[0].content).toBe('the final answer');
  });

  it('marks the run failed and keeps the error message', () => {
    const prev: MessageType[] = [pendingRun('AR-1')];
    const next = upsertAgentRunStatusFromSocket(prev, {
      type: 'agent_run_status',
      agent_run_id: 'AR-1',
      conversation_id: 'CONV-1',
      status: 'failed',
      error: 'provider exploded',
    });
    expect(next[0].runStatus).toBe('Failed');
    expect(next[0].error).toBe('provider exploded');
  });

  it('does not duplicate an already reconciled message on success', () => {
    const prev: MessageType[] = [
      {
        key: 'AM-1',
        from: 'assistant',
        versions: [{ id: 'AM-1', content: 'the final answer' }],
      },
    ];
    const next = upsertAgentRunStatusFromSocket(prev, {
      type: 'agent_run_status',
      agent_run_id: 'AR-1',
      conversation_id: 'CONV-1',
      status: 'Success',
      response: 'the final answer',
      agent_message_id: 'AM-1',
    });
    expect(next).toHaveLength(1);
  });

  it('ignores events without an agent_run_id', () => {
    const prev: MessageType[] = [pendingRun('AR-1')];
    const next = upsertAgentRunStatusFromSocket(prev, {
      type: 'agent_run_status',
      conversation_id: 'CONV-1',
      status: 'success',
    });
    expect(next).toBe(prev);
  });
});

describe('mergePendingRunsIntoMessages', () => {
  it('creates user and assistant bubbles from a Queued run when no messages exist', () => {
    const runs: PendingConversationRun[] = [
      { name: 'AR-1', status: 'Queued', prompt: 'hello', sequence: 1 },
    ];
    const next = mergePendingRunsIntoMessages([], runs, []);
    expect(next).toHaveLength(2);
    expect(next[0]).toMatchObject({ from: 'user', agentRunId: 'AR-1', versions: [{ content: 'hello' }] });
    expect(next[1]).toMatchObject({ key: 'AR-1', from: 'assistant', runStatus: 'Queued' });
  });

  it('skips runs already represented by a persisted assistant message', () => {
    const runs: PendingConversationRun[] = [
      { name: 'AR-1', status: 'Started', prompt: 'hello', sequence: 1 },
    ];
    const conversationItems: ChatMessage[] = [
      {
        id: 'AM-1',
        conversation: 'CONV-1',
        content: 'done',
        isAgent: true,
        agentRun: 'AR-1',
      },
    ];
    const next = mergePendingRunsIntoMessages([], runs, conversationItems);
    expect(next).toHaveLength(0);
  });

  it('is idempotent when pending assistant bubble already exists', () => {
    const runs: PendingConversationRun[] = [
      { name: 'AR-1', status: 'Started', prompt: 'hello', sequence: 1 },
    ];
    const prev: MessageType[] = [pendingRun('AR-1')];
    const next = mergePendingRunsIntoMessages(prev, runs, []);
    expect(next).toHaveLength(2);
    expect(next.filter((msg) => msg.key === 'AR-1')).toHaveLength(1);
    expect(next.find((msg) => msg.key === 'AR-1')?.runStatus).toBe('Started');
  });

  it('does not duplicate the user bubble when it already exists in conversation items', () => {
    const runs: PendingConversationRun[] = [
      { name: 'AR-1', status: 'Started', prompt: 'hello', sequence: 1 },
    ];
    const conversationItems: ChatMessage[] = [
      {
        id: 'UM-1',
        conversation: 'CONV-1',
        content: 'hello',
        isAgent: false,
      },
    ];
    const next = mergePendingRunsIntoMessages([], runs, conversationItems);
    expect(next).toHaveLength(1);
    expect(next[0]).toMatchObject({ key: 'AR-1', from: 'assistant', runStatus: 'Started' });
  });
});

describe('mergeConversationItemsIntoMessages', () => {
  it('keeps pending assistant bubbles during merge', () => {
    const prev: MessageType[] = [pendingRun('AR-1')];
    const conversationItems: ChatMessage[] = [
      {
        id: 'UM-1',
        conversation: 'CONV-1',
        content: 'hello',
        isAgent: false,
      },
    ];
    const next = mergeConversationItemsIntoMessages(prev, conversationItems, false);
    expect(next).toHaveLength(2);
    expect(next[1]).toMatchObject({ key: 'AR-1', runStatus: 'Queued' });
  });

  it('keeps user bubbles linked to an open run when user message is not persisted yet', () => {
    const prev: MessageType[] = [
      {
        key: 'user-temp',
        from: 'user',
        agentRunId: 'AR-1',
        versions: [{ id: 'user-temp', content: 'hello' }],
      },
      pendingRun('AR-1'),
    ];
    const conversationItems: ChatMessage[] = [];
    const next = mergeConversationItemsIntoMessages(prev, conversationItems, false);
    expect(next).toHaveLength(2);
    expect(next[0].agentRunId).toBe('AR-1');
  });

  it('drops hydrated user bubbles once the persisted user message is available', () => {
    const prev: MessageType[] = [
      {
        key: 'pending-user-AR-1',
        from: 'user',
        agentRunId: 'AR-1',
        versions: [{ id: 'pending-user-AR-1', content: 'hello' }],
      },
      pendingRun('AR-1'),
    ];
    const conversationItems: ChatMessage[] = [
      {
        id: 'UM-1',
        conversation: 'CONV-1',
        content: 'hello',
        isAgent: false,
        agentRun: 'AR-1',
      },
    ];
    const next = mergeConversationItemsIntoMessages(prev, conversationItems, false);
    expect(next).toHaveLength(2);
    expect(next[0].key).toBe('UM-1');
    expect(next.find((msg) => msg.key === 'pending-user-AR-1')).toBeUndefined();
  });

  it('maps agentRunId onto assistant messages from conversation items', () => {
    const conversationItems: ChatMessage[] = [
      {
        id: 'AM-1',
        conversation: 'CONV-1',
        content: 'assistant response',
        isAgent: true,
        agentRun: 'AR-100',
      },
    ];
    const next = mergeConversationItemsIntoMessages([], conversationItems, false);
    expect(next).toHaveLength(1);
    expect(next[0].from).toBe('assistant');
    expect(next[0].agentRunId).toBe('AR-100');
  });
});

describe('applyPolledRunStatus', () => {
  it('transitions a pending run to Started', () => {
    const prev: MessageType[] = [pendingRun('AR-1')];
    const next = applyPolledRunStatus(
      prev,
      {
        success: true,
        queued: true,
        status: 'Started',
        agent_run_id: 'AR-1',
        conversation_id: 'CONV-1',
      },
      'CONV-1'
    );
    expect(next[0].runStatus).toBe('Started');
  });

  it('applies Success content and reconciles the bubble to the persisted message id', () => {
    const prev: MessageType[] = [pendingRun('AR-1')];
    const next = applyPolledRunStatus(
      prev,
      {
        success: true,
        queued: false,
        status: 'Success',
        response: 'polled answer',
        agent_run_id: 'AR-1',
        conversation_id: 'CONV-1',
        agent_message_id: 'AM-9',
      },
      'CONV-1'
    );
    expect(next).toHaveLength(1);
    expect(next[0].key).toBe('AM-9');
    expect(next[0].runStatus).toBeUndefined();
    expect(next[0].versions[0].id).toBe('AM-9');
    expect(next[0].versions[0].content).toBe('polled answer');
  });

  it('keeps the run-keyed bubble when Success has no agent_message_id', () => {
    const prev: MessageType[] = [pendingRun('AR-1')];
    const next = applyPolledRunStatus(
      prev,
      {
        success: true,
        queued: false,
        status: 'Success',
        response: 'polled answer',
        agent_run_id: 'AR-1',
        conversation_id: 'CONV-1',
        agent_message_id: null,
      },
      'CONV-1'
    );
    expect(next[0].key).toBe('AR-1');
    expect(next[0].runStatus).toBe('Success');
    expect(next[0].versions[0].content).toBe('polled answer');
  });

  it('marks the run Failed with the backend error string', () => {
    const prev: MessageType[] = [pendingRun('AR-1')];
    const next = applyPolledRunStatus(
      prev,
      {
        success: true,
        queued: false,
        status: 'Failed',
        error: 'worker died',
        agent_run_id: 'AR-1',
        conversation_id: 'CONV-1',
      },
      'CONV-1'
    );
    expect(next[0].runStatus).toBe('Failed');
    expect(next[0].error).toBe('worker died');
  });

  it('ignores payloads from a different conversation', () => {
    const prev: MessageType[] = [pendingRun('AR-1')];
    const next = applyPolledRunStatus(
      prev,
      {
        success: true,
        queued: false,
        status: 'Success',
        response: 'nope',
        agent_run_id: 'AR-1',
        conversation_id: 'CONV-2',
        agent_message_id: 'AM-9',
      },
      'CONV-1'
    );
    expect(next).toBe(prev);
  });
});
