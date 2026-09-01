import type { ToolCallEvent, NewAgentMessageEvent, AgentRunStatusEvent } from '@/hooks/useChatSocket';
import type { AgentRunStatusResponse, ChatMessage, PendingConversationRun } from '@/services/chatApi';
import type { ToolUIPart } from 'ai';
import { mapToolStatusToState } from './utils';
import type { MessageType } from './types';

// Reasoning text is streamed client-side only and is NOT persisted on the server.
// When ChatMessageList remounts (e.g. after new-conversation navigation), prev=[],
// so the normal key-based lookup loses the reasoning. This cache bridges the gap:
// ChatInput writes here when streaming ends; the mapper reads it as a fallback.
const _reasoningCache = new Map<string, string>();
export function cacheReasoning(messageId: string, reasoning: string): void {
  _reasoningCache.set(messageId, reasoning);
}
function consumeReasoningCache(messageId: string): string | undefined {
  const r = _reasoningCache.get(messageId);
  if (r !== undefined) _reasoningCache.delete(messageId);
  return r;
}

/** Normalize socket event - backend may send `status`/`result` instead of `tool_status`/`tool_result` */
function normalizeToolCallEvent(raw: Record<string, unknown>): ToolCallEvent {
  const tool_status =
    (raw.tool_status as string) ?? (raw.status as string) ?? 'Queued';
  let tool_result = raw.tool_result as Record<string, unknown> | undefined;
  if (!tool_result && typeof raw.result === 'string') {
    try {
      const parsed = JSON.parse(raw.result);
      tool_result = parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : undefined;
    } catch {
      tool_result = { output: raw.result };
    }
  }
  return {
    ...raw,
    agent_run_id: (raw.agent_run_id as string) ?? '',
    conversation_id: (raw.conversation_id as string) ?? '',
    message_id: (raw.message_id as string) ?? (raw.agent_run_id as string) ?? '',
    tool_call_id: (raw.tool_call_id as string) ?? '',
    tool_name: (raw.tool_name as string) ?? 'unknown',
    tool_status: tool_status as ToolCallEvent['tool_status'],
    tool_args: raw.tool_args as Record<string, unknown> | undefined,
    tool_result,
    error: (raw.error as string | null) ?? undefined,
  } as ToolCallEvent;
}

function safeParseJsonRecord(value: unknown): Record<string, unknown> {
  if (!value) return {};
  if (typeof value === 'object') return value as Record<string, unknown>;
  if (typeof value !== 'string') return {};

  try {
    const parsed = JSON.parse(value);
    if (parsed && typeof parsed === 'object') return parsed as Record<string, unknown>;
    return {};
  } catch {
    return {};
  }
}

function safeStringify(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** Terminal states where a tool's elapsed run time can be finalized. */
const TOOL_TERMINAL_STATES = new Set<ToolUIPart['state']>(['output-available', 'output-error']);

/**
 * Frontend-only approximation of tool duration: stamps `startedAt` the first time a tool
 * reaches "input-available" (running), then derives `durationMs` once it reaches a terminal
 * state. Not exact server timing, but close enough for a lightweight footnote display.
 */
function computeToolTiming(
  existing: { startedAt?: number; durationMs?: number } | undefined,
  newStatus: ToolUIPart['state']
): { startedAt?: number; durationMs?: number } {
  const startedAt = existing?.startedAt ?? (newStatus === 'input-available' ? Date.now() : undefined);
  let durationMs = existing?.durationMs;
  if (durationMs === undefined && TOOL_TERMINAL_STATES.has(newStatus) && startedAt !== undefined) {
    durationMs = Math.max(0, Date.now() - startedAt);
  }
  return { startedAt, durationMs };
}

export function upsertToolUpdateFromSocket(prev: MessageType[], rawEvent: ToolCallEvent | Record<string, unknown>): MessageType[] {
  const event = normalizeToolCallEvent(
    typeof rawEvent?.type === 'string' ? (rawEvent as Record<string, unknown>) : (rawEvent as Record<string, unknown>)
  );

  // Skip events with no meaningful identifiers
  if (!event.tool_call_id && !event.tool_name) return prev;
  const displayName = event.tool_name && event.tool_name !== 'unknown' ? event.tool_name : 'Tool';

  const parsedArgs = safeParseJsonRecord(event.tool_args);
  const parsedResult = event.tool_result ? safeStringify(event.tool_result) : undefined;
  const newStatus = mapToolStatusToState(event.tool_status) as ToolUIPart['state'];

  // Find message: 1) by agent_run_id, 2) by tool_call_id in any message's tools
  let messageIndex = event.agent_run_id
    ? prev.findIndex((msg) => msg.key === event.agent_run_id)
    : -1;
  if (messageIndex < 0 && event.tool_call_id) {
    messageIndex = prev.findIndex(
      (msg) => msg.tools?.some((t: { tool_call_id?: string }) => t.tool_call_id === event.tool_call_id)
    );
  }

  // Update existing assistant message
  if (messageIndex >= 0) {
    const message = prev[messageIndex];
    const existingTools = message.tools || [];
    let toolIndex = event.tool_call_id
      ? existingTools.findIndex((t: { tool_call_id?: string }) => t.tool_call_id === event.tool_call_id)
      : -1;
    // Only fall back to name-based matching when the event itself carries no
    // tool_call_id (older/incomplete events). If the event *does* have an id
    // but it doesn't match any existing tool, this is a genuinely new call
    // (e.g. the same tool invoked twice in one turn) — matching by name here
    // would silently overwrite the earlier call's args/result.
    if (toolIndex < 0 && !event.tool_call_id) {
      toolIndex = existingTools.findIndex(
        (t: { name?: string }) => t.name === displayName || t.name === event.tool_name
      );
    }

    const existingTool = toolIndex >= 0 ? existingTools[toolIndex] : undefined;
    const { startedAt, durationMs } = computeToolTiming(existingTool, newStatus);

    const updatedTool = {
      tool_call_id: event.tool_call_id,
      name: displayName,
      description: displayName,
      status: newStatus,
      parameters: parsedArgs,
      result: event.tool_status === 'Completed' ? parsedResult : undefined,
      error: event.tool_status === 'Failed' ? (event.error || parsedResult) : undefined,
      startedAt,
      durationMs,
    };

    const updatedTools = [...existingTools];
    if (toolIndex >= 0) updatedTools[toolIndex] = updatedTool;
    else updatedTools.push(updatedTool);

    const isImageGeneration = event.tool_name === 'generate_image' && event.type === 'tool_call_started';

    const updated = [...prev];
    updated[messageIndex] = {
      ...message,
      kind: isImageGeneration ? 'Image' : message.kind,
      tools: updatedTools,
    };
    return updated;
  }

  // Don't create new message if we have no agent_run_id (completed event without started)
  if (!event.agent_run_id) return prev;

  const { startedAt, durationMs } = computeToolTiming(undefined, newStatus);
  const updatedTool = {
    tool_call_id: event.tool_call_id,
    name: displayName,
    description: displayName,
    status: newStatus,
    parameters: parsedArgs,
    result: event.tool_status === 'Completed' ? parsedResult : undefined,
    error: event.tool_status === 'Failed' ? (event.error || parsedResult) : undefined,
    startedAt,
    durationMs,
  };

  const isImageGeneration = event.tool_name === 'generate_image' && event.type === 'tool_call_started';
  const newMessage: MessageType = {
    key: event.agent_run_id,
    from: 'assistant',
    agentRunId: event.agent_run_id,
    kind: isImageGeneration ? 'Image' : undefined,
    versions: [
      {
        id: event.message_id || event.agent_run_id,
        content: '',
      },
    ],
    tools: [updatedTool],
  };
  return [...prev, newMessage];
}

/** Canonical run lifecycle statuses match the Agent Run doctype Select options. */
const CANONICAL_RUN_STATUSES: Record<string, AgentRunStatusEvent['status']> = {
  queued: 'Queued',
  started: 'Started',
  success: 'Success',
  failed: 'Failed',
};

function normalizeAgentRunStatusEvent(raw: Record<string, unknown>): AgentRunStatusEvent {
  const rawStatus = typeof raw.status === 'string' ? raw.status : '';
  const status =
    CANONICAL_RUN_STATUSES[rawStatus.trim().toLowerCase()] ??
    (rawStatus as AgentRunStatusEvent['status']) ??
    'Queued';
  return {
    ...raw,
    type: 'agent_run_status',
    agent_run_id: (raw.agent_run_id as string) ?? '',
    conversation_id: (raw.conversation_id as string) ?? '',
    session_id: raw.session_id as string | undefined,
    status,
    response: raw.response as string | undefined,
    error: raw.error as string | undefined,
    agent_message_id: raw.agent_message_id as string | undefined,
    sequence: typeof raw.sequence === 'number' ? raw.sequence : undefined,
  } as AgentRunStatusEvent;
}

export function upsertAgentRunStatusFromSocket(
  prev: MessageType[],
  rawEvent: AgentRunStatusEvent | Record<string, unknown>
): MessageType[] {
  const event = normalizeAgentRunStatusEvent(
    typeof rawEvent?.type === 'string' ? (rawEvent as Record<string, unknown>) : (rawEvent as Record<string, unknown>)
  );

  if (!event.agent_run_id) return prev;

  const runIndex = prev.findIndex((msg) => msg.key === event.agent_run_id);

  const createPendingMessage = (content: string = ''): MessageType => ({
    key: event.agent_run_id,
    from: 'assistant',
    runStatus: event.status,
    agentRunId: event.agent_run_id,
    versions: [{ id: event.agent_run_id, content }],
  });

  if (event.status === 'Queued' || event.status === 'Started') {
    if (runIndex >= 0) {
      const updated = [...prev];
      updated[runIndex] = {
        ...updated[runIndex],
        runStatus: event.status,
        agentRunId: event.agent_run_id || updated[runIndex].agentRunId,
      };
      return updated;
    }
    return [...prev, createPendingMessage()];
  }

  if (event.status === 'Success') {
    if (runIndex < 0) {
      // If the persisted message already reconciled with this run, don't create a duplicate.
      if (event.agent_message_id && prev.some((msg) => msg.versions.some((v) => v.id === event.agent_message_id))) {
        return prev;
      }
      return [...prev, createPendingMessage(event.response ?? '')];
    }
    const updated = [...prev];
    const existing = updated[runIndex];
    updated[runIndex] = {
      ...existing,
      runStatus: 'Success',
      agentRunId: event.agent_run_id || existing.agentRunId,
      versions: existing.versions.map((v, i) =>
        i === 0 ? { ...v, content: event.response ?? v.content } : v
      ),
    };
    return updated;
  }

  if (event.status === 'Failed') {
    let targetIndex = runIndex;
    if (targetIndex < 0 && event.agent_message_id) {
      targetIndex = prev.findIndex(
        (msg) =>
          msg.key === event.agent_message_id ||
          msg.versions.some((v) => v.id === event.agent_message_id)
      );
    }
    if (targetIndex < 0) {
      return [
        ...prev,
        {
          key: event.agent_run_id,
          from: 'assistant',
          runStatus: 'Failed',
          agentRunId: event.agent_run_id,
          error: event.error,
          versions: [{ id: event.agent_run_id, content: event.error ?? '' }],
        },
      ];
    }
    const updated = [...prev];
    updated[targetIndex] = {
      ...updated[targetIndex],
      runStatus: 'Failed',
      agentRunId: event.agent_run_id || updated[targetIndex].agentRunId,
      error: event.error,
    };
    return updated;
  }

  return prev;
}

export function upsertAgentMessageFromSocket(prev: MessageType[], event: NewAgentMessageEvent): MessageType[] {
  let messageIndex = prev.findIndex((msg) => msg.versions.some((v) => v.id === event.message_id));

  if (messageIndex < 0 && event.agent_run_id) {
    messageIndex = prev.findIndex((msg) => msg.key === event.agent_run_id);
  }

  if (messageIndex >= 0) {
    const updated = [...prev];
    const existing = updated[messageIndex];
    updated[messageIndex] = {
      ...existing,
      key: event.message_id,
      kind: event.kind,
      generatedImage: event.generated_image,
      generatedAudio: event.generated_audio,
      generatedVideo: event.generated_video,
      injected_memories: event.injected_memories,
      agentRunId: event.agent_run_id || existing.agentRunId,
      runStatus: undefined,
      error: undefined,
      versions: existing.versions.map((v) =>
        v.id === event.message_id || v.id === event.agent_run_id
          ? { ...v, id: event.message_id, content: event.content ?? v.content }
          : v
      ),
    };
    return updated;
  }

  const newMessage: MessageType = {
    key: event.message_id,
    from: 'assistant',
    kind: event.kind,
    generatedImage: event.generated_image,
    generatedAudio: event.generated_audio,
    generatedVideo: event.generated_video,
    injected_memories: event.injected_memories,
    agentRunId: event.agent_run_id,
    versions: [
      {
        id: event.message_id,
        content: event.content || '',
      },
    ],
  };
  return [...prev, newMessage];
}

/**
 * Apply a polled agent run status as the same state transition the socket
 * handlers would produce. Reuses the socket mappers so the reconciliation
 * logic stays in one place:
 * - the run status event updates the pending bubble (keyed by agent_run_id);
 * - on Success with an agent_message_id, the follow-up new message event
 *   reconciles the bubble with the persisted Agent Message.
 */
export function applyPolledRunStatus(
  prev: MessageType[],
  poll: AgentRunStatusResponse,
  conversationId: string
): MessageType[] {
  // Ignore status payloads that belong to another conversation.
  if (poll.conversation_id && poll.conversation_id !== conversationId) {
    return prev;
  }

  const eventConversationId = poll.conversation_id ?? conversationId;

  const withStatus = upsertAgentRunStatusFromSocket(prev, {
    type: 'agent_run_status',
    agent_run_id: poll.agent_run_id,
    conversation_id: eventConversationId,
    status: poll.status,
    response: poll.response ?? undefined,
    error: poll.error ?? undefined,
    agent_message_id: poll.agent_message_id ?? undefined,
  });

  if (poll.status === 'Success' && poll.agent_message_id) {
    return upsertAgentMessageFromSocket(withStatus, {
      type: 'new_agent_message',
      conversation_id: eventConversationId,
      message_id: poll.agent_message_id,
      content: poll.response ?? '',
      agent_run_id: poll.agent_run_id,
    });
  }

  return withStatus;
}

const PENDING_RUN_STATUSES = new Set<MessageType['runStatus']>(['Queued', 'Started']);

function isPendingRunMessage(msg: MessageType): boolean {
  return msg.runStatus === 'Queued' || msg.runStatus === 'Started';
}

function normalizeRunStatus(status: string): 'Queued' | 'Started' | null {
  const normalized = CANONICAL_RUN_STATUSES[status.trim().toLowerCase()];
  if (normalized === 'Queued' || normalized === 'Started') {
    return normalized;
  }
  return null;
}

export function filterMessagesForConversation(
  conversationItems: ChatMessage[],
  conversationId: string
): ChatMessage[] {
  return conversationItems.filter((item) => item.conversation === conversationId);
}

export function hasStaleConversationItems(
  conversationItems: ChatMessage[],
  conversationId: string
): boolean {
  return (
    conversationItems.length > 0 &&
    !conversationItems.some((item) => item.conversation === conversationId)
  );
}

function messageContent(msg: MessageType): string {
  return msg.versions[0]?.content?.trim() ?? '';
}

function hasPersistedUserForRun(
  run: PendingConversationRun,
  conversationItems: ChatMessage[],
  prev: MessageType[]
): boolean {
  const prompt = run.prompt?.trim();
  if (!prompt) {
    return false;
  }

  if (
    conversationItems.some(
      (item) =>
        !item.isAgent &&
        (item.agentRun === run.name || item.content?.trim() === prompt)
    )
  ) {
    return true;
  }

  return prev.some(
    (msg) =>
      msg.from === 'user' &&
      (msg.agentRunId === run.name || messageContent(msg) === prompt)
  );
}

function isHydratedUserMessageKey(key: string): boolean {
  return key.startsWith('pending-user-');
}

/**
 * Rebuild pending user/assistant bubbles from open Agent Run records.
 * Idempotent: skips runs already represented in prev or conversationItems.
 */
export function mergePendingRunsIntoMessages(
  prev: MessageType[],
  runs: PendingConversationRun[],
  conversationItems: ChatMessage[]
): MessageType[] {
  if (runs.length === 0) {
    return prev;
  }

  const completedAssistantRunIds = new Set(
    conversationItems
      .filter((item) => item.isAgent && item.agentRun)
      .map((item) => item.agentRun as string)
  );

  const runsToHydrate = runs
    .map((run) => ({ run, status: normalizeRunStatus(run.status) }))
    .filter((entry): entry is { run: PendingConversationRun; status: 'Queued' | 'Started' } =>
      entry.status !== null
    )
    .filter(({ run }) => !completedAssistantRunIds.has(run.name))
    .filter(({ run }) => !run.prompt?.startsWith('[SILENT_TRIGGER]'))
    .sort((a, b) => {
      const seqA = a.run.sequence ?? 0;
      const seqB = b.run.sequence ?? 0;
      if (seqA !== seqB) return seqA - seqB;
      return a.run.name.localeCompare(b.run.name);
    });

  if (runsToHydrate.length === 0) {
    return prev;
  }

  let result = [...prev];
  const existingKeys = new Set(prev.map((msg) => msg.key));

  for (const { run, status } of runsToHydrate) {
    const prompt = run.prompt?.trim();
    if (prompt && !hasPersistedUserForRun(run, conversationItems, result)) {
      const userKey = `pending-user-${run.name}`;
      if (!existingKeys.has(userKey)) {
        result.push({
          key: userKey,
          from: 'user',
          agentRunId: run.name,
          versions: [{ id: userKey, content: prompt }],
        });
        existingKeys.add(userKey);
      }
    }

    if (!existingKeys.has(run.name)) {
      result.push({
        key: run.name,
        from: 'assistant',
        runStatus: status,
        agentRunId: run.name,
        versions: [{ id: run.name, content: '' }],
      });
      existingKeys.add(run.name);
    } else {
      result = result.map((msg) =>
        msg.key === run.name && PENDING_RUN_STATUSES.has(msg.runStatus)
          ? { ...msg, runStatus: status }
          : msg
      );
    }
  }

  return result;
}

/**
 * Collapse consecutive "tool-only" messages (persisted as one Agent Message
 * per tool call, kind "Tool Result") that share an agent_run_id into a
 * single message with a combined `tools[]` array — matching how the live
 * socket path already accumulates a run's tool calls onto one message (see
 * upsertToolUpdateFromSocket above). Without this, reloading a conversation
 * from history renders one bubble per tool call instead of one per run.
 */
function mergeToolCallGroups(messages: MessageType[]): MessageType[] {
  const grouped: MessageType[] = [];
  const groupIndexByRun = new Map<string, number>();

  for (const msg of messages) {
    // A persisted "Tool Result" message's `content` field holds a narrative
    // description of the call ("Requesting Tool: X\n...\n**Tool Result:**\n
    // {...}"), not an empty string — checking for empty content here always
    // evaluated false, so this whole grouping branch silently never ran.
    // `kind` is the reliable signal: only genuine "Tool Result" records
    // should collapse together, never a real assistant "Message" that
    // happens to carry temp `tools[]` state.
    const isToolOnly = !!msg.tools?.length && msg.kind === 'Tool Result';

    if (isToolOnly) {
      // Prefer grouping by agent_run_id when the backend provided one, but
      // fall back to merging with the immediately preceding tool-only
      // message when it's absent — otherwise every tool call persisted
      // without a run id renders as its own bubble (see the "many single
      // frappe_get_record rows" bug report).
      const previous = grouped[grouped.length - 1];
      const fallbackMergeable = !msg.agentRunId && previous &&
        !!previous.tools?.length &&
        previous.kind === 'Tool Result' &&
        !previous.agentRunId;

      const existingIndex = msg.agentRunId
        ? groupIndexByRun.get(msg.agentRunId)
        : fallbackMergeable
          ? grouped.length - 1
          : undefined;

      if (existingIndex !== undefined) {
        const existing = grouped[existingIndex];
        const toolMap = new Map((existing.tools || []).map((t) => [t.tool_call_id, t]));
        msg.tools!.forEach((t) => toolMap.set(t.tool_call_id, t));
        grouped[existingIndex] = { ...existing, tools: Array.from(toolMap.values()) };
        continue;
      }
      if (msg.agentRunId) groupIndexByRun.set(msg.agentRunId, grouped.length);
    }

    grouped.push(msg);
  }

  return grouped;
}

export function mergeConversationItemsIntoMessages(
  prev: MessageType[],
  conversationItems: ChatMessage[],
  preserveDuringTransition: boolean = false
): MessageType[] {
  // During transition, if API returns empty, preserve all existing messages
  if (preserveDuringTransition && conversationItems.length === 0) {
    return prev;
  }

  // If we have no items to merge, return previous messages (preserve state)
  if (conversationItems.length === 0) {
    return prev;
  }

  const mapped: MessageType[] = conversationItems.map((item) => {
    const tempMessage = prev.find((msg) => msg.key === item.id);
    const tempTools = tempMessage?.tools || [];

    const baseMessage: MessageType = {
      key: item.id,
      from: item.isAgent ? 'assistant' : 'user',
      agentRunId: item.agentRun,
      kind: item.kind,
      generatedImage: item.generatedImage,
      generatedAudio: item.generatedAudio,
      generatedVideo: item.generatedVideo,
      voiceMessage: item.voiceMessage,
      sttModel: item.sttModel,
      status: item.status,
      injected_memories: item.injectedMemories,
      // Reasoning/thinking text is streamed client-side only (not persisted
      // server-side), so it must be carried over from the prior local
      // message the same way tools are, or it vanishes the moment the
      // conversation is re-synced from the server after the run completes.
      reasoning: tempMessage?.reasoning ?? consumeReasoningCache(item.id),
      reasoningStreaming: tempMessage?.reasoningStreaming,
      versions: [
        {
          id: item.id,
          content: item.content,
        },
      ],
    };

    if (item.kind === 'Tool Result' && item.toolName) {
      const parsedArgs = safeParseJsonRecord(item.toolArgs);

      const tempTool = tempTools.find((tool) => tool.name === item.toolName);
      const tool_call_id = tempTool?.tool_call_id || `temp-${item.id}-${item.toolName}`;

      const apiTool = {
        tool_call_id,
        name: item.toolName,
        description: item.toolName,
        status: mapToolStatusToState(item.toolStatus) as ToolUIPart['state'],
        parameters: parsedArgs,
        result: item.toolStatus === 'Completed' ? item.content : undefined,
        error: item.toolStatus === 'Failed' ? item.content : undefined,
      };

      const toolMap = new Map<string, typeof apiTool>();
      tempTools.forEach((tool) => {
        toolMap.set(tool.tool_call_id, tool);
      });

      if (!toolMap.has(tool_call_id)) toolMap.set(tool_call_id, apiTool);

      baseMessage.tools = Array.from(toolMap.values());
    } else if (tempTools.length > 0) {
      baseMessage.tools = tempTools;
    }

    return baseMessage;
  });

  const apiMessageIds = new Set(conversationItems.map((item) => item.id));

  const shouldPreserveTempMessage = (msg: MessageType): boolean => {
    if (apiMessageIds.has(msg.key)) return false;
    if (isPendingRunMessage(msg)) return true;
    if (msg.tools && msg.tools.length > 0) return true;

    const runId = msg.agentRunId ?? (isHydratedUserMessageKey(msg.key)
      ? msg.key.slice('pending-user-'.length)
      : undefined);
    const content = messageContent(msg);

    if (runId || isHydratedUserMessageKey(msg.key)) {
      const userPersisted = conversationItems.some(
        (item) =>
          !item.isAgent &&
          (item.agentRun === runId ||
            (content.length > 0 && item.content?.trim() === content))
      );
      if (!userPersisted) return true;
    }

    return false;
  };

  // During transition, preserve all messages not in API response
  // Otherwise, preserve pending runs, linked user bubbles, and tool UI state
  const remainingTempMessages = preserveDuringTransition
    ? prev.filter((msg) => !apiMessageIds.has(msg.key))
    : prev.filter(shouldPreserveTempMessage);

  return [...mergeToolCallGroups(mapped), ...remainingTempMessages];
}
