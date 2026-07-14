import type { ToolCallEvent, NewAgentMessageEvent, AgentRunStatusEvent } from '@/hooks/useChatSocket';
import type { ChatMessage } from '@/services/chatApi';
import { mapToolStatusToState } from './utils';
import type { MessageType } from './types';

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

export function upsertToolUpdateFromSocket(prev: MessageType[], rawEvent: ToolCallEvent | Record<string, unknown>): MessageType[] {
  const event = normalizeToolCallEvent(
    typeof rawEvent?.type === 'string' ? (rawEvent as Record<string, unknown>) : (rawEvent as Record<string, unknown>)
  );

  // Skip events with no meaningful identifiers
  if (!event.tool_call_id && !event.tool_name) return prev;
  const displayName = event.tool_name && event.tool_name !== 'unknown' ? event.tool_name : 'Tool';

  const parsedArgs = safeParseJsonRecord(event.tool_args);
  const parsedResult = event.tool_result ? safeStringify(event.tool_result) : undefined;

  const updatedTool = {
    tool_call_id: event.tool_call_id,
    name: displayName,
    description: displayName,
    status: mapToolStatusToState(event.tool_status) as any,
    parameters: parsedArgs,
    result: event.tool_status === 'Completed' ? parsedResult : undefined,
    error: event.tool_status === 'Failed' ? (event.error || parsedResult) : undefined,
  };

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
    if (toolIndex < 0) {
      toolIndex = existingTools.findIndex(
        (t: { name?: string }) => t.name === displayName || t.name === event.tool_name
      );
    }

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

  const isImageGeneration = event.tool_name === 'generate_image' && event.type === 'tool_call_started';
  const newMessage: MessageType = {
    key: event.agent_run_id,
    from: 'assistant',
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
    versions: [{ id: event.agent_run_id, content }],
  });

  if (event.status === 'Queued' || event.status === 'Started') {
    if (runIndex >= 0) {
      const updated = [...prev];
      updated[runIndex] = { ...updated[runIndex], runStatus: event.status };
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
          error: event.error,
          versions: [{ id: event.agent_run_id, content: event.error ?? '' }],
        },
      ];
    }
    const updated = [...prev];
    updated[targetIndex] = {
      ...updated[targetIndex],
      runStatus: 'Failed',
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
    versions: [
      {
        id: event.message_id,
        content: event.content || '',
      },
    ],
  };
  return [...prev, newMessage];
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
      kind: item.kind,
      generatedImage: item.generatedImage,
      generatedAudio: item.generatedAudio,
      generatedVideo: item.generatedVideo,
      voiceMessage: item.voiceMessage,
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
        status: mapToolStatusToState(item.toolStatus) as any,
        parameters: parsedArgs,
        result: item.toolStatus === 'Completed' ? item.content : undefined,
        error: item.toolStatus === 'Failed' ? item.content : undefined,
      };

      const toolMap = new Map<string, typeof apiTool>();
      tempTools.forEach((tool) => {
        toolMap.set(tool.tool_call_id, tool as any);
      });

      if (!toolMap.has(tool_call_id)) toolMap.set(tool_call_id, apiTool);

      baseMessage.tools = Array.from(toolMap.values());
    } else if (tempTools.length > 0) {
      baseMessage.tools = tempTools;
    }

    return baseMessage;
  });

  const apiMessageIds = new Set(conversationItems.map((item) => item.id));
  
  // During transition, preserve all messages not in API response
  // Otherwise, only preserve temporary messages with tools
  const remainingTempMessages = preserveDuringTransition
    ? prev.filter((msg) => !apiMessageIds.has(msg.key))
    : prev.filter(
        (msg) => !apiMessageIds.has(msg.key) && msg.tools && msg.tools.length > 0
      );

  return [...mapped, ...remainingTempMessages];
}

