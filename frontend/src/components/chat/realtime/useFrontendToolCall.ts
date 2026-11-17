import { useCallback } from 'react';
import type { FrontendToolCallEvent } from '@/hooks/useChatSocket';
import { executeClientToolCall } from '@/lib/clientToolDispatcher';

/** Handle backend-initiated client-side ("frontend") tool calls. */
export function useFrontendToolCall(chatId?: string | null) {
  return useCallback((event: FrontendToolCallEvent) => {
    if (event.conversation_id !== chatId) return;

    const callId = event.tool_call_ref ?? event.call_id;
    if (!callId) return;

    void executeClientToolCall({
      callId,
      functionName: event.function_name,
      toolParams: event.tool_params,
    });
  }, [chatId]);
}
