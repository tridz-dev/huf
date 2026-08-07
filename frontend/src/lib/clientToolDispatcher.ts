/**
 * Client Tool Dispatcher
 *
 * The backend announces a client-side ("frontend") tool call on two
 * channels: the `frontend_tool_call_initiated` socket event, and the
 * `client_side_tool_calls` array on the send-message / new-conversation
 * HTTP response. Realtime events in this codebase are explicitly
 * best-effort (see doc/domain/queue-first-execution-model.md design rule 4:
 * "Pending-state UI must reconcile via polling, not rely on the socket
 * alone"), so a dropped socket event must not leave a tool call unexecuted
 * forever -- the HTTP response is a second chance to pick it up.
 *
 * This module is the single execution path for both channels, sharing one
 * de-duplication set so a call that arrives on both runs exactly once.
 */

import { getClientTool } from '@/lib/clientToolRegistry';
import { submitClientToolResult, type ClientToolCallPayload } from '@/services/chatApi';

export type { ClientToolCallPayload };

export interface ClientToolCallRequest {
  callId: string;
  functionName: string;
  toolParams?: Record<string, unknown>;
}

// Socket events are best-effort/at-least-once, and the same call can also
// show up in the HTTP response payload, so tracking must be shared across
// both channels rather than kept per-component.
const executedCallIds = new Set<string>();

/**
 * Clear tracked call ids. Call when the active conversation changes so the
 * set doesn't grow for the lifetime of the app and doesn't leak ids across
 * unrelated conversations.
 */
export function resetClientToolCallTracking(): void {
  executedCallIds.clear();
}

/**
 * Synchronous check-then-add so two events landing in the same tick (one
 * from each channel) cannot both pass.
 */
function claimClientToolCall(callId: string): boolean {
  if (executedCallIds.has(callId)) return false;
  executedCallIds.add(callId);
  return true;
}

/**
 * Release a claimed call id. Used after a failed *submit* (not a failed
 * handler) so a later retry -- e.g. the response-payload reconciliation path
 * -- can attempt the call again instead of it being permanently marked done.
 */
function releaseClientToolCall(callId: string): void {
  executedCallIds.delete(callId);
}

/** Submit a result, reporting whether the submit itself succeeded. */
async function trySubmitClientToolResult(
  params: Parameters<typeof submitClientToolResult>[0]
): Promise<boolean> {
  try {
    await submitClientToolResult(params);
    return true;
  } catch {
    return false;
  }
}

/**
 * Execute a client-side ("frontend") tool call and submit its result back to
 * the backend. Shared by both the socket path (`frontend_tool_call_initiated`)
 * and the HTTP response path (`client_side_tool_calls`).
 *
 * De-duplicates against concurrent/duplicate delivery, keeps the call marked
 * as claimed while execution and the initial submit are in flight, and
 * releases it again if the submit fails so a later retry can still run it.
 * Never throws into the caller.
 */
export async function executeClientToolCall({
  callId,
  functionName,
  toolParams,
}: ClientToolCallRequest): Promise<void> {
  if (!callId) return;
  if (!claimClientToolCall(callId)) return;

  const handler = getClientTool(functionName);
  if (!handler) {
    const submitted = await trySubmitClientToolResult({
      callId,
      error: `No client tool handler registered for "${functionName}"`,
    });
    if (!submitted) releaseClientToolCall(callId);
    return;
  }

  try {
    const result = await handler(toolParams ?? {});
    const submitted = await trySubmitClientToolResult({ callId, result });
    if (!submitted) releaseClientToolCall(callId);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const submitted = await trySubmitClientToolResult({ callId, error: message });
    if (!submitted) releaseClientToolCall(callId);
  }
}

/**
 * Execute every entry in a `client_side_tool_calls` array from a
 * send-message / new-conversation HTTP response. Parses each entry's
 * JSON-string `arguments` (guarding against invalid JSON) and dispatches
 * through `executeClientToolCall`, so a call already handled via the socket
 * is skipped by the shared de-duplication.
 */
export function executeClientToolCallsFromResponse(
  calls: ClientToolCallPayload[] | undefined | null
): void {
  if (!calls?.length) return;

  for (const call of calls) {
    const callId = call.id;
    if (!callId) continue;

    let toolParams: Record<string, unknown> = {};
    try {
      const parsed = JSON.parse(call.function?.arguments || '{}');
      if (parsed && typeof parsed === 'object') {
        toolParams = parsed as Record<string, unknown>;
      }
    } catch {
      // Malformed arguments JSON -- proceed with empty params so the
      // handler (or the missing-handler path) still runs and reports a
      // meaningful error instead of the call being silently dropped.
    }

    void executeClientToolCall({
      callId,
      functionName: call.function?.name ?? '',
      toolParams,
    });
  }
}
