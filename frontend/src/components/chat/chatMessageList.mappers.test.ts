import { describe, it, expect } from 'vitest';
import { upsertAgentRunStatusFromSocket } from './chatMessageList.mappers';
import type { MessageType } from './types';

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
