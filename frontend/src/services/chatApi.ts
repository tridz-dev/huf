import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import { PaginationParams, PaginatedResponse } from '@/types/pagination';
import { fetchDocCount } from './utilsApi';

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
  /**
   * Raw timestamp (ISO/datetime string from Frappe).
   * Use `timestampLabel` for display-friendly formatting.
   */
  timestamp?: string;
  /**
   * UI-friendly label (e.g. "2m ago"). Populated by UI hooks.
   */
  timestampLabel?: string;
}

type ConversationFilter = [keyof AgentConversationDoc | string, string, unknown];

export interface AgentMessageDoc {
  name: string;
  conversation: string;
  content: string;
  is_agent_message?: 0 | 1 | string;
  kind?: string;
  generated_image?: string;
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
  generatedImage?: string;
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
    generatedImage: doc.generated_image,
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
 * Agent with conversation count (for "By Agent" tab)
 */
export interface AgentWithCount {
  name: string;
  agent_name: string;
  conversationCount: number;
  last_updated?: string;
}

/**
 * Fetch agents sorted by last updated, with conversation counts.
 * Used for "By Agent" tab to show agents without loading all conversations.
 */
export async function getAgentsWithConversationCounts(): Promise<AgentWithCount[]> {
  try {
    // Fetch all agents sorted by last updated (modified field)
    const agents = await db.getDocList(doctype.Agent, {
      fields: ['name', 'agent_name', 'modified'],
      orderBy: { field: 'modified', order: 'asc' },
      limit: 1000, // Reasonable limit for agents
    });

    // Fetch conversation count for each agent
    const agentsWithCounts: AgentWithCount[] = await Promise.all(
      (agents as Array<{ name: string; agent_name: string; modified?: string }>).map(async (agent) => {
        const count = await fetchDocCount(doctype['Agent Conversation'], [
          ['agent', '=', agent.name],
          ['channel', '=', 'Chat'],
        ]);
        return {
          name: agent.name,
          agent_name: agent.agent_name || agent.name,
          conversationCount: count || 0,
          last_updated: agent.modified,
        };
      })
    );

    // Filter out agents with 0 conversations and sort by last updated
    return agentsWithCounts
      .filter((agent) => agent.conversationCount > 0)
      .sort((a, b) => {
        const aTime = a.last_updated ? new Date(a.last_updated).getTime() : 0;
        const bTime = b.last_updated ? new Date(b.last_updated).getTime() : 0;
        return bTime - aTime; // Descending (newest first)
      });
  } catch (error) {
    handleFrappeError(error, 'Error fetching agents with conversation counts');
    return [];
  }
}

/**
 * Fetch conversations for a specific agent.
 * Used for lazy loading when user opens an agent accordion.
 */
export async function getConversationsByAgent(
  agentName: string,
  params: { limit?: number; start?: number } = {}
): Promise<PaginatedResponse<ChatListItem>> {
  const { limit = 100, start = 0 } = params;

  try {
    const conversations = await db.getDocList(doctype['Agent Conversation'], {
      fields: ['name', 'title', 'agent', 'last_activity', 'modified'],
      filters: [
        ['agent', '=', agentName],
        ['channel', '=', 'Chat'],
      ],
      orderBy: { field: 'modified', order: 'desc' },
      limit,
      limit_start: start,
    });

    const mapped = (conversations as AgentConversationDoc[]).map(mapChatListItem);
    return {
      data: mapped,
      hasMore: mapped.length === limit,
    };
  } catch (error) {
    handleFrappeError(error, `Error fetching conversations for agent ${agentName}`);
    return {
      data: [],
      hasMore: false,
    };
  }
}

/**
 * Fetch all conversations for date grouping (Recents tab).
 * Fetches a large batch to properly group by date.
 */
export async function getAllConversationsForRecents(
  limit: number = 500
): Promise<ChatListItem[]> {
  try {
    const conversations = await db.getDocList(doctype['Agent Conversation'], {
      fields: ['name', 'title', 'agent', 'last_activity', 'modified'],
      filters: [['channel', '=', 'Chat']],
      orderBy: { field: 'modified', order: 'desc' },
      limit,
    });

    return (conversations as AgentConversationDoc[]).map(mapChatListItem);
  } catch (error) {
    handleFrappeError(error, 'Error fetching all conversations for recents');
    return [];
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
      fields: ['name', 'conversation', 'content', 'is_agent_message', 'kind', 'generated_image', 'tool_name', 'tool_status', 'tool_args', 'creation', 'modified'],
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
