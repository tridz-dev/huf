import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { AgentToolFunctionRef, AgentToolType } from '@/types/agent.types';
import { handleFrappeError } from '@/lib/frappe-error';

/**
 * Fetch all available tool types from Frappe
 */
export async function getToolTypes(): Promise<AgentToolType[]> {
  try {
    const toolTypes = await db.getDocList(doctype['Agent Tool Type'], {
      fields: ['name', 'name1'],
      limit: 1000,
    });
    return toolTypes as AgentToolType[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching tool types');
  }
}

/**
 * Fetch all available tool functions from Frappe
 * Only fetches: name, description, and tool_type
 * Optionally filter by tool_type
 */
export async function getToolFunctions(toolTypeFilter?: string): Promise<AgentToolFunctionRef[]> {
  try {
    const options = {
      fields: ["name", "description", "tool_type"],
      limit: 1000,
      filters: [] as any,
    };
    if (toolTypeFilter && options.filters) {
      options.filters.push({ field: 'tool_type', operator: '=', value: toolTypeFilter });
    }

    const tools = await db.getDocList(doctype['Agent Tool Function'], options);
    return tools as AgentToolFunctionRef[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching tool functions');
  }
}
