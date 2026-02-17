import type { ToolCallEvent, NewAgentMessageEvent } from '@/hooks/useChatSocket';
import type { ChatMessage } from '@/services/chatApi';
import { mapToolStatusToState } from './utils';
import type { MessageType } from './types';

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

export function upsertToolUpdateFromSocket(prev: MessageType[], event: ToolCallEvent): MessageType[] {
  const parsedArgs = safeParseJsonRecord(event.tool_args);
  const parsedResult = event.tool_result ? safeStringify(event.tool_result) : undefined;

  const updatedTool = {
    tool_call_id: event.tool_call_id,
    name: event.tool_name,
    description: event.tool_name,
    status: mapToolStatusToState(event.tool_status) as any,
    parameters: parsedArgs,
    result: event.tool_status === 'Completed' ? parsedResult : undefined,
    error: event.tool_status === 'Failed' ? (event.error || parsedResult) : undefined,
  };

  const messageIndex = prev.findIndex((msg) => msg.key === event.agent_run_id);

  // Update existing assistant run message
  if (messageIndex >= 0) {
    const message = prev[messageIndex];
    const existingTools = message.tools || [];
    const toolIndex = existingTools.findIndex((tool) => tool.name === event.tool_name);

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

  // Otherwise create a temporary assistant message for the tool call
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

export function upsertAgentMessageFromSocket(prev: MessageType[], event: NewAgentMessageEvent): MessageType[] {
  const messageIndex = prev.findIndex((msg) => msg.versions.some((v) => v.id === event.message_id));

  if (messageIndex >= 0) {
    const updated = [...prev];
    updated[messageIndex] = {
      ...updated[messageIndex],
      kind: event.kind,
      generatedImage: event.generated_image,
      versions: updated[messageIndex].versions.map((v) =>
        v.id === event.message_id ? { ...v, content: event.content || v.content } : v
      ),
    };
    return updated;
  }

  const newMessage: MessageType = {
    key: event.message_id,
    from: 'assistant',
    kind: event.kind,
    generatedImage: event.generated_image,
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

