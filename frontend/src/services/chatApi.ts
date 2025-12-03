import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import { PaginationParams, PaginatedResponse } from '@/types/pagination';

/**
 * Agent Conversation document from Frappe
 */
export interface AgentConversationDoc {
  name: string;
  title: string;
  agent: string;
  last_activity?: string;
  modified?: string;
}

/**
 * Chat list item (mapped from Agent Conversation)
 */
export interface ChatListItem {
  id: string;
  title: string;
  agent: string;
  timestamp?: string;
}

type ConversationFilter = [keyof AgentConversationDoc | string, string, unknown];

export interface AgentMessageDoc {
  name: string;
  conversation: string;
  content: string;
  is_agent_message?: 0 | 1 | string;
  kind?: string;
  tool_name?: string;
  tool_status?: string;
  tool_args?: string | Record<string, unknown>;
  creation?: string;
  modified?: string;
}

export interface ChatMessage {
  id: string;
  conversation: string;
  content: string;
  isAgent: boolean;
  kind?: string;
  toolName?: string;
  toolStatus?: string;
  toolArgs?: string | Record<string, unknown>;
  createdAt?: string;
  updatedAt?: string;
}

/**
 * Map Agent Conversation document to chat list item
 */
function mapChatListItem(doc: AgentConversationDoc): ChatListItem {
  return {
    id: doc.name,
    title: doc.title || 'Untitled Chat',
    agent: doc.agent || '',
    timestamp: doc.last_activity || doc.modified || undefined,
  };
}

function mapAgentMessage(doc: AgentMessageDoc): ChatMessage {
  const isAgent = doc.is_agent_message === 1;

  return {
    id: doc.name,
    conversation: doc.conversation,
    content: doc.content || '',
    isAgent,
    kind: doc.kind,
    toolName: doc.tool_name,
    toolStatus: doc.tool_status,
    toolArgs: doc.tool_args,
    createdAt: doc.creation,
    updatedAt: doc.modified,
  };
}

/**
 * Parameters for fetching paginated conversations
 */
export interface ConversationListParams extends PaginationParams {
  filters?: ConversationFilter[];
}

export interface ConversationMessageListParams extends PaginationParams {
  conversation?: string;
}

/**
 * Fetch paginated agent conversations sorted by last updated time.
 */
export async function getConversations(
  params: ConversationListParams = {}
): Promise<PaginatedResponse<ChatListItem>> {
  const { limit = 20, start = 0, search, filters } = params;

  try {
    const effectiveFilters =
      (filters as any[] | undefined) ??
      (search ? ([['title', 'like', `%${search}%`]] as any[]) : undefined);

    const conversations = await db.getDocList(doctype['Agent Conversation'], {
      fields: ['name', 'title', 'agent', 'last_activity', 'modified'],
      orderBy: { field: 'modified', order: 'desc' },
      limit,
      limit_start: start,
      filters: effectiveFilters,
    });

    const mapped = (conversations as AgentConversationDoc[]).map(mapChatListItem);
    return {
      data: mapped,
      hasMore: mapped.length === limit,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching conversations');
  }
}

/**
 * Fetch a single conversation
 */
export async function getConversation(conversationId: string): Promise<AgentConversationDoc | undefined> {
  try {
    const conversation = await db.getDoc(doctype['Agent Conversation'], conversationId);
    return conversation as AgentConversationDoc;
  } catch (error) {
    handleFrappeError(error, 'Error fetching conversation');
  }
}

/**
 * Load messages for a specific conversation, ordered from newest to oldest
 */
export async function getConversationMessages(
  params: ConversationMessageListParams
): Promise<PaginatedResponse<ChatMessage>> {
  const { conversation, limit = 30, start = 0 } = params;

  if (!conversation) {
    return {
      data: [],
      hasMore: false,
      total: 0,
    };
  }

  try {
    const messages = await db.getDocList(doctype['Agent Message'], {
      fields: ['name', 'conversation', 'content', 'is_agent_message', 'kind', 'tool_name', 'tool_status', 'tool_args', 'creation', 'modified'],
      filters: [['conversation', '=', conversation]],
      orderBy: { field: 'creation', order: 'desc' },
      limit,
      limit_start: start,
    });

    const mapped = (messages as AgentMessageDoc[]).map(mapAgentMessage);
    const ordered = mapped.slice().reverse();

    return {
      data: ordered,
      hasMore: mapped.length === limit,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching conversation messages');
  }
}

/**
 * Start a new conversation
 */
export interface NewConversationParams {
  agent: string;
  message: string;
}

export interface NewConversationResponse {
  message: {
    success: boolean;
    conversation_id: string;
    run: {
      success: boolean;
      response: string;
      structured: unknown;
      provider: string;
      agent_run_id: string;
      conversation_id: string;
      session_id: string;
    };
  };
}

/**
 * Send message to an existing conversation
 */
export interface SendMessageParams {
  conversation: string;
  message: string;
}

export interface SendMessageResponse {
  message: {
    success: boolean;
    response: string;
    structured: unknown;
    provider: string;
    agent_run_id: string;
    conversation_id: string;
    session_id: string;
  };
}

/**
 * Start a new conversation
 */
export async function newConversation(
  params: NewConversationParams
): Promise<NewConversationResponse> {
  try {
    const result = await call.post('huf.ai.agent_chat.new_conversation', {
      agent: params.agent,
      message: params.message,
    });
    return result as NewConversationResponse;
  } catch (error) {
    handleFrappeError(error, 'Error creating new conversation');
  }
}

/**
 * Send a message to an existing conversation
 */
export async function sendMessageToConversation(
  params: SendMessageParams
): Promise<SendMessageResponse> {
  try {
    const result = await call.post('huf.ai.agent_chat.send_message_to_conversation', {
      conversation: params.conversation,
      message: params.message,
    });
    return result as SendMessageResponse;
  } catch (error) {
    handleFrappeError(error, 'Error sending message to conversation');
  }
}

/**
 * Submit agent run feedback
 */
export interface AgentRunFeedbackParams {
  agent: string;
  feedback: 'Thumbs Up' | 'Thumbs Down';
  comments?: string;
  conversation?: string;
  agent_message?: string;
}

export async function createAgentRunFeedback(params: AgentRunFeedbackParams): Promise<void> {
  try {
    await db.createDoc('Agent Run Feedback', {
      agent: params.agent,
      feedback: params.feedback,
      comments: params.comments,
      conversation: params.conversation,
      agent_message: params.agent_message,
    });
  } catch (error) {
    handleFrappeError(error, 'Error submitting feedback');
  }
}
