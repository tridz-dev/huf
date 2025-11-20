import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';

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
 * Fetch all agent conversations
 * Sorted by last updated (modified field)
 */
export async function getConversations(): Promise<ChatListItem[]> {
  try {
    const conversations = await db.getDocList(doctype['Agent Conversation'], {
      fields: ['name', 'title', 'agent', 'last_activity', 'modified'],
      orderBy: { field: 'modified', order: 'desc' },
      limit: 1000,
    });
    return (conversations as AgentConversationDoc[]).map(mapChatListItem);
  } catch (error) {
    handleFrappeError(error, 'Error fetching conversations');
  }
}




