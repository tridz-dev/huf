import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';

/**
 * Agent Run document from Frappe for dashboard
 */
export interface AgentRunDoc {
  name: string;
  agent: string;
  conversation?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  status?: string;
}

/**
 * Fetch the last 10 agent runs for dashboard
 */
export async function getRecentAgentRuns(): Promise<AgentRunDoc[]> {
  try {
    const runs = await db.getDocList(doctype["Agent Run"], {
      fields: ['name', 'agent', 'conversation', 'start_time', 'end_time', 'status'],
      limit: 10,
      orderBy: { field: 'creation', order: 'desc' },
    });
    
    return runs as AgentRunDoc[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching recent agent runs');
    return [];
  }
}

