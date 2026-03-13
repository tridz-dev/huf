/**
 * SSE streaming API for agent chat.
 * Provides real-time streaming with REST fallback.
 */

import {
  newConversation,
  sendMessageToConversation,
  type NewConversationResponse,
  type SendMessageResponse,
} from './chatApi';

const frappeUrl = import.meta.env.VITE_FRAPPE_URL || window.location.origin;

/** Module-level flag: set once at app load, read by ChatInput */
export let streamingAvailable = false;

export function setStreamingAvailable(value: boolean): void {
  streamingAvailable = value;
}

export interface StreamChunk {
  type: 'delta' | 'tool_call' | 'complete' | 'error';
  content?: string;
  full_response?: string;
  response?: string;
  conversation_id?: string;
  success?: boolean;
  agent_run_id?: string;
  session_id?: string;
  provider?: string;
  error?: string;
  tool_call?: { function?: { name?: string } };
}

function getCsrfToken(): string {
  return (window as any).csrf_token || '';
}

/**
 * Check if streaming endpoint is available. Call once at app load.
 */
export async function checkStreamingAvailable(): Promise<boolean> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 3000);

  try {
    const res = await fetch(`${frappeUrl}/ivendnext_ai_agents/stream/ping`, {
      method: 'GET',
      credentials: 'include',
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (res.ok) {
      const data = await res.json();
      return data?.ok === true || data?.status === 'ok';
    }
    return false;
  } catch {
    clearTimeout(timeout);
    return false;
  }
}

export interface StreamAgentParams {
  agentName: string;
  message: string;
  conversationId?: string;
}

/**
 * Stream agent response via SSE. Yields chunks and returns final result.
 */
export async function* streamAgentResponse(
  params: StreamAgentParams
): AsyncGenerator<StreamChunk, StreamChunk | undefined, unknown> {
  const { agentName, message, conversationId } = params;
  const url = `${frappeUrl}/ivendnext_ai_agents/stream/${encodeURIComponent(agentName)}`;

  const body: Record<string, unknown> = {
    prompt: message,
    channel_id: 'Chat',
  };
  if (conversationId) {
    body.conversation_id = conversationId;
  } else {
    body.create_new = true;
  }

  const res = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': getCsrfToken(),
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    yield { type: 'error', error: `Request failed: ${res.status}` };
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    yield { type: 'error', error: 'No response body' };
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6)) as StreamChunk;
          yield data;
          if (data.type === 'complete' || data.type === 'error') {
            return data;
          }
        } catch {
          // Skip malformed lines
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  return undefined;
}

export type ChatResult = NewConversationResponse | SendMessageResponse;

export interface SendMessageOptions {
  useStreaming: boolean;
  onDelta?: (text: string) => void;
}

/**
 * Unified sendMessage: same response shape for SSE and REST.
 */
export async function sendMessage(
  params: { agent: string; message: string; conversationId?: string },
  options: SendMessageOptions
): Promise<ChatResult> {
  const { useStreaming, onDelta } = options;

    if (useStreaming) {
    let lastComplete: StreamChunk | undefined;
    for await (const chunk of streamAgentResponse({
      agentName: params.agent,
      message: params.message,
      conversationId: params.conversationId,
    })) {
      if (chunk.type === 'delta' && onDelta && chunk.full_response !== undefined) {
        onDelta(chunk.full_response);
      }
      if (chunk.type === 'complete') {
        lastComplete = chunk;
        if (onDelta) {
          const final =
            chunk.response ?? chunk.full_response ?? '';
          if (final) onDelta(final);
        }
        break;
      }
      if (chunk.type === 'error') {
        throw new Error(chunk.error ?? 'Stream error');
      }
    }

    if (!lastComplete) {
      throw new Error('Stream ended without complete event');
    }

    const data = lastComplete;
    const runShape = {
      success: data.success ?? true,
      response: data.response ?? data.full_response ?? '',
      conversation_id: data.conversation_id,
      agent_run_id: data.agent_run_id,
      session_id: data.session_id,
      provider: data.provider,
      structured: null as unknown,
    };

    if (params.conversationId) {
      return {
        message: {
          success: true,
          response: runShape.response,
          conversation_id: data.conversation_id ?? '',
          agent_run_id: data.agent_run_id ?? '',
          session_id: data.session_id ?? '',
          provider: data.provider ?? '',
          structured: null,
        },
      } as SendMessageResponse;
    }

    return {
      message: {
        success: true,
        conversation_id: data.conversation_id ?? '',
        run: runShape,
      },
    } as NewConversationResponse;
  }

  if (params.conversationId) {
    return sendMessageToConversation({
      conversation: params.conversationId,
      message: params.message,
    }) as Promise<SendMessageResponse>;
  }

  return newConversation({
    agent: params.agent,
    message: params.message,
  }) as Promise<NewConversationResponse>;
}
