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
  type: 'delta' | 'reasoning' | 'tool_call' | 'complete' | 'error';
  content?: string;
  full_response?: string;
  full_reasoning?: string;
  reasoning_content?: string;
  response?: string;
  conversation_id?: string;
  success?: boolean;
  agent_run_id?: string;
  agent_message_id?: string;
  session_id?: string;
  provider?: string;
  error?: string;
  tool_call?: { function?: { name?: string } };
}

type FrappeWindow = Window & {
  csrf_token?: string;
};

function getCsrfToken(): string {
  return (window as FrappeWindow).csrf_token || '';
}

/**
 * True for a fetch/stream rejection caused by an AbortController we fired
 * ourselves (user-initiated stop), as opposed to a real network/server
 * failure. Browsers throw a DOMException named "AbortError"; some fetch
 * polyfills throw a plain Error with the same name, so check by name only.
 */
function isAbortError(err: unknown): boolean {
  return typeof err === 'object' && err !== null && 'name' in err && (err as { name?: unknown }).name === 'AbortError';
}

/**
 * Check if streaming endpoint is available. Call once at app load.
 */
export async function checkStreamingAvailable(): Promise<boolean> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 3000);

  try {
    const res = await fetch(`${frappeUrl}/huf/stream/ping`, {
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

export interface StreamAgentFile {
  file_id: string;
  file_url: string;
  filename: string;
  is_image: number;
}

export interface StreamAgentParams {
  agentName: string;
  message: string;
  conversationId?: string;
  skipUserMessage?: boolean;
  files?: StreamAgentFile[];
  modelOverride?: string;
  /**
   * User-triggered cancellation signal (e.g. a "Stop" button), distinct from
   * the internal 3s connectivity guard used elsewhere in this module.
   */
  signal?: AbortSignal;
}

/**
 * Stream agent response via SSE. Yields chunks and returns final result.
 */
export async function* streamAgentResponse(
  params: StreamAgentParams
): AsyncGenerator<StreamChunk, StreamChunk | undefined, unknown> {
  const { agentName, message, conversationId, skipUserMessage, files, modelOverride, signal } = params;
  const url = `${frappeUrl}/huf/stream/${encodeURIComponent(agentName)}`;

  const body: Record<string, unknown> = {
    prompt: message,
    channel_id: 'Chat',
  };
  if (conversationId) {
    body.conversation_id = conversationId;
  } else {
    body.create_new = true;
  }
  if (skipUserMessage) {
    body.skip_user_message = true;
  }
  if (files?.length) {
    body.files = files;
  }
  if (modelOverride) {
    body.model_override = modelOverride;
  }

  const res = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': getCsrfToken(),
    },
    body: JSON.stringify(body),
    signal,
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
  onReasoningDelta?: (text: string) => void;
  skipUserMessage?: boolean;
  files?: StreamAgentFile[];
  /** User-triggered cancellation signal for the streaming path (SSE only). */
  signal?: AbortSignal;
}

/**
 * Unified sendMessage: same response shape for SSE and REST.
 */
export async function sendMessage(
  params: {
    agent: string;
    message: string;
    conversationId?: string;
    skipUserMessage?: boolean;
    files?: StreamAgentFile[];
    modelOverride?: string;
  },
  options: SendMessageOptions
): Promise<ChatResult> {
  const { useStreaming, onDelta, onReasoningDelta, skipUserMessage, files, signal } = options;
  const streamSkip = params.skipUserMessage ?? skipUserMessage;
  const streamFiles = params.files ?? files;

    if (useStreaming) {
    let lastComplete: StreamChunk | undefined;
    // Tracks the latest partial text so a user-initiated stop can still
    // return a well-formed "complete" result with whatever arrived so far,
    // instead of losing it or surfacing as an error.
    let lastPartialResponse = '';
    let lastPartialReasoning: string | undefined;
    try {
      for await (const chunk of streamAgentResponse({
        agentName: params.agent,
        message: params.message,
        conversationId: params.conversationId,
        skipUserMessage: streamSkip,
        files: streamFiles,
        modelOverride: params.modelOverride,
        signal,
      })) {
        if (chunk.type === 'delta' && chunk.full_response !== undefined) {
          lastPartialResponse = chunk.full_response;
          onDelta?.(chunk.full_response);
        }
        if (chunk.type === 'reasoning' && chunk.full_reasoning !== undefined) {
          lastPartialReasoning = chunk.full_reasoning;
          onReasoningDelta?.(chunk.full_reasoning);
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
    } catch (err) {
      // User-initiated cancellation is a normal outcome, not a failure: keep
      // whatever partial text/reasoning already streamed in and synthesize a
      // successful completion instead of propagating the abort as an error.
      if (isAbortError(err) || signal?.aborted) {
        lastComplete = {
          type: 'complete',
          success: true,
          full_response: lastPartialResponse,
          response: lastPartialResponse,
          full_reasoning: lastPartialReasoning,
        };
      } else {
        throw err;
      }
    }

    if (!lastComplete) {
      throw new Error('Stream ended without complete event');
    }

    const data = lastComplete;
    const runShape = {
      success: data.success ?? true,
      response: data.response ?? data.full_response ?? '',
      error: data.error ?? null,
      conversation_id: data.conversation_id,
      agent_run_id: data.agent_run_id,
      agent_message_id: data.agent_message_id,
      session_id: data.session_id,
      provider: data.provider,
      structured: null as unknown,
    };

    if (params.conversationId) {
      return {
        message: {
          success: runShape.success,
          queued: false,
          status: runShape.success ? 'Success' : 'Failed',
          response: runShape.response,
          error: runShape.error ?? undefined,
          conversation_id: data.conversation_id ?? '',
          agent_run_id: data.agent_run_id ?? '',
          agent_message_id: data.agent_message_id ?? '',
          session_id: data.session_id ?? '',
          provider: data.provider ?? '',
          structured: null,
        },
      } as SendMessageResponse;
    }

    return {
      message: {
        success: runShape.success,
        queued: false,
        status: runShape.success ? 'Success' : 'Failed',
        conversation_id: data.conversation_id ?? '',
        agent_message_id: data.agent_message_id ?? '',
        run: runShape,
      },
    } as NewConversationResponse;
  }

  if (params.conversationId) {
    return sendMessageToConversation({
      conversation: params.conversationId,
      message: params.message,
      skip_user_message: streamSkip,
      files: streamFiles,
      modelOverride: params.modelOverride,
    }) as Promise<SendMessageResponse>;
  }

  return newConversation({
    agent: params.agent,
    message: params.message,
    skip_user_message: streamSkip,
    files: streamFiles,
    modelOverride: params.modelOverride,
  }) as Promise<NewConversationResponse>;
}
