import { describe, it, expect, vi, beforeEach } from 'vitest';

const { submitClientToolResultMock } = vi.hoisted(() => ({
  submitClientToolResultMock: vi.fn(),
}));

vi.mock('@/services/chatApi', () => ({
  submitClientToolResult: submitClientToolResultMock,
}));

const { getClientToolMock } = vi.hoisted(() => ({
  getClientToolMock: vi.fn(),
}));

vi.mock('@/lib/clientToolRegistry', () => ({
  getClientTool: getClientToolMock,
}));

import {
  executeClientToolCall,
  executeClientToolCallsFromResponse,
  resetClientToolCallTracking,
} from './clientToolDispatcher';

describe('clientToolDispatcher', () => {
  beforeEach(() => {
    submitClientToolResultMock.mockReset();
    getClientToolMock.mockReset();
    resetClientToolCallTracking();
  });

  it('executes the handler and submits its result', async () => {
    const handler = vi.fn().mockResolvedValue({ ok: true });
    getClientToolMock.mockReturnValue(handler);
    submitClientToolResultMock.mockResolvedValue({ success: true });

    await executeClientToolCall({ callId: 'call-1', functionName: 'doThing', toolParams: { a: 1 } });

    expect(handler).toHaveBeenCalledWith({ a: 1 });
    expect(submitClientToolResultMock).toHaveBeenCalledWith({ callId: 'call-1', result: { ok: true } });
  });

  it('submits an error when no handler is registered', async () => {
    getClientToolMock.mockReturnValue(undefined);
    submitClientToolResultMock.mockResolvedValue({ success: true });

    await executeClientToolCall({ callId: 'call-2', functionName: 'missingTool' });

    expect(submitClientToolResultMock).toHaveBeenCalledWith({
      callId: 'call-2',
      error: 'No client tool handler registered for "missingTool"',
    });
  });

  it('de-duplicates the same call id arriving twice, running the handler once', async () => {
    const handler = vi.fn().mockResolvedValue('done');
    getClientToolMock.mockReturnValue(handler);
    submitClientToolResultMock.mockResolvedValue({ success: true });

    await Promise.all([
      executeClientToolCall({ callId: 'call-3', functionName: 'doThing' }),
      executeClientToolCall({ callId: 'call-3', functionName: 'doThing' }),
    ]);

    expect(handler).toHaveBeenCalledTimes(1);
    expect(submitClientToolResultMock).toHaveBeenCalledTimes(1);
  });

  it('releases the call id on a failed submit so a retry can run the handler again', async () => {
    const handler = vi.fn().mockResolvedValue('done');
    getClientToolMock.mockReturnValue(handler);
    submitClientToolResultMock.mockRejectedValueOnce(new Error('network error'));
    submitClientToolResultMock.mockResolvedValueOnce({ success: true });

    await executeClientToolCall({ callId: 'call-4', functionName: 'doThing' });
    expect(handler).toHaveBeenCalledTimes(1);

    await executeClientToolCall({ callId: 'call-4', functionName: 'doThing' });
    expect(handler).toHaveBeenCalledTimes(2);
    expect(submitClientToolResultMock).toHaveBeenCalledTimes(2);
  });

  it('clears tracking across conversations via resetClientToolCallTracking', async () => {
    const handler = vi.fn().mockResolvedValue('done');
    getClientToolMock.mockReturnValue(handler);
    submitClientToolResultMock.mockResolvedValue({ success: true });

    await executeClientToolCall({ callId: 'call-5', functionName: 'doThing' });
    resetClientToolCallTracking();
    await executeClientToolCall({ callId: 'call-5', functionName: 'doThing' });

    expect(handler).toHaveBeenCalledTimes(2);
  });

  it('parses JSON-string arguments from the HTTP response payload', () => {
    const handler = vi.fn().mockResolvedValue('done');
    getClientToolMock.mockReturnValue(handler);
    submitClientToolResultMock.mockResolvedValue({ success: true });

    executeClientToolCallsFromResponse([
      {
        id: 'call-6',
        type: 'function',
        function: { name: 'doThing', arguments: '{"x":42}' },
        tool_call_ref: 'ATC-0001',
      },
    ]);

    return vi.waitFor(() => {
      expect(handler).toHaveBeenCalledWith({ x: 42 });
    });
  });

  it('falls back to empty params when arguments JSON is malformed', () => {
    const handler = vi.fn().mockResolvedValue('done');
    getClientToolMock.mockReturnValue(handler);
    submitClientToolResultMock.mockResolvedValue({ success: true });

    executeClientToolCallsFromResponse([
      {
        id: 'call-7',
        type: 'function',
        function: { name: 'doThing', arguments: 'not json' },
      },
    ]);

    return vi.waitFor(() => {
      expect(handler).toHaveBeenCalledWith({});
    });
  });

  it('skips a call already claimed by the socket channel (shared de-duplication)', async () => {
    const handler = vi.fn().mockResolvedValue('done');
    getClientToolMock.mockReturnValue(handler);
    submitClientToolResultMock.mockResolvedValue({ success: true });

    await executeClientToolCall({ callId: 'call-8', functionName: 'doThing' });

    executeClientToolCallsFromResponse([
      {
        id: 'call-8',
        type: 'function',
        function: { name: 'doThing', arguments: '{}' },
      },
    ]);

    await vi.waitFor(() => {
      expect(handler).toHaveBeenCalledTimes(1);
    });
  });
});
