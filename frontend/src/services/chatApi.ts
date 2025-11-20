import { db } from '@/lib/frappe-sdk';
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

type ConversationFilter = [keyof AgentConversationDoc | string, 'like', string];

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

/**
 * Parameters for fetching paginated conversations
 */
export interface ConversationListParams extends PaginationParams {}

/**
 * Fetch paginated agent conversations sorted by last updated time.
 */
export async function getConversations(
  params: ConversationListParams = {}
): Promise<PaginatedResponse<ChatListItem>> {
  const { limit = 20, start = 0, search } = params;

  try {
    const filters: ConversationFilter[] | undefined = search
      ? [['title', 'like', `%${search}%`]]
      : undefined;

    const conversations = await db.getDocList(doctype['Agent Conversation'], {
      fields: ['name', 'title', 'agent', 'last_activity', 'modified'],
      orderBy: { field: 'modified', order: 'desc' },
      limit,
      limit_start: start,
      filters,
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
