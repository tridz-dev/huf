import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { AgentDoc } from '@/types/agent.types';

/**
 * Trigger type from API
 */
export interface TriggerTypeOption {
  name: string;
}

/**
 * Fetch trigger types from API
 */
export async function getTriggerTypes(): Promise<TriggerTypeOption[]> {
  try {
    const result = await call.get('agentflo.agentflo.doctype.agent_trigger.agent_trigger.get_trigger_type');
    // Handle different response formats
    // Frappe API might return { message: [...] } or just the array directly
    return result.message as TriggerTypeOption[];
  } catch (error) {
    console.error('Error fetching trigger types:', error);
    throw error;
  }
}

/**
 * Fields needed for the agents list page
 */
const AGENT_LIST_FIELDS = [
  'name',
  'agent_name',
  'description',
  'model',
  'disabled',
  'last_run',
  'total_run',
];

/**
 * Fields needed for agent triggers listing
 */
const AGENT_TRIGGER_FIELDS = [
  'name',
  'trigger_name',
  'trigger_type',
  'disabled',
];

/**
 * Agent Trigger document from Frappe (for listing)
 */
export interface AgentTriggerListItem {
  name: string;
  trigger_name: string;
  type: string;
  status: 'active' | 'disabled';
}

/**
 * Map Agent Trigger doctype document to listing format
 */
function mapAgentTriggerListItem(doc: {
  name: string;
  trigger_name: string;
  trigger_type?: string;
  disabled?: 0 | 1;
}): AgentTriggerListItem {
  return {
    name: doc.name,
    trigger_name: doc.trigger_name,
    type: doc.trigger_type || 'Manual',
    status: doc.disabled === 1 ? 'disabled' : 'active',
  };
}

/**
 * Fetch agents from Frappe
 */
export async function getAgents(): Promise<AgentDoc[]> {
  try {
    const agents = await db.getDocList(doctype.Agent, {
      fields: AGENT_LIST_FIELDS,
      limit: 1000,
    });
    return agents as AgentDoc[];
  } catch (error) {
    console.error('Error fetching agents:', error);
    throw error;
  }
}

/**
 * Fetch a single agent by name
 * Fetches all fields for detail view
 */
export async function getAgent(name: string): Promise<AgentDoc> {
  try {
    const agent = await db.getDoc(doctype.Agent, name);
    return agent as AgentDoc;
  } catch (error) {
    console.error(`Error fetching agent ${name}:`, error);
    throw error;
  }
}

/**
 * Agent Trigger document from Frappe (for editing)
 */
export interface AgentTriggerDoc {
  name: string;
  trigger_name: string;
  agent: string;
  trigger_type?: string;
  disabled?: 0 | 1;
  scheduled_interval?: string;
  interval_count?: number;
  reference_doctype?: string;
  doc_event?: string;
  condition?: string;
}

/**
 * Fetch a single agent trigger by name
 */
export async function getAgentTrigger(triggerName: string): Promise<AgentTriggerDoc> {
  try {
    const trigger = await db.getDoc(doctype['Agent Trigger'], triggerName);
    return trigger as AgentTriggerDoc;
  } catch (error) {
    console.error(`Error fetching trigger ${triggerName}:`, error);
    throw error;
  }
}

/**
 * Create a new agent trigger
 */
export async function createAgentTrigger(data: Partial<AgentTriggerDoc>): Promise<AgentTriggerDoc> {
  try {
    const newTrigger = await db.createDoc(doctype['Agent Trigger'], data);
    return newTrigger as AgentTriggerDoc;
  } catch (error) {
    console.error('Error creating agent trigger:', error);
    throw error;
  }
}

/**
 * Update an agent trigger
 */
export async function updateAgentTrigger(name: string, data: Partial<AgentTriggerDoc>): Promise<AgentTriggerDoc> {
  try {
    await db.updateDoc(doctype['Agent Trigger'], name, data);
    const updatedTrigger = await db.getDoc(doctype['Agent Trigger'], name);
    return updatedTrigger as AgentTriggerDoc;
  } catch (error) {
    console.error(`Error updating trigger ${name}:`, error);
    throw error;
  }
}

/**
 * Fetch all DocTypes (for reference_doctype select)
 */
export async function getDocTypes(): Promise<Array<{ name: string }>> {
  try {
    const doctypes = await db.getDocList('DocType', {
      fields: ['name'],
      limit: 1000,
    });
    // Sort alphabetically by name
    return (doctypes as Array<{ name: string }>).sort((a, b) => a.name.localeCompare(b.name));
  } catch (error) {
    console.error('Error fetching DocTypes:', error);
    throw error;
  }
}

/**
 * Fetch agent triggers filtered by agent name (for listing)
 */
export async function getAgentTriggers(agentName: string): Promise<AgentTriggerListItem[]> {
  try {
    const triggers = await db.getDocList(doctype['Agent Trigger'], {
      fields: AGENT_TRIGGER_FIELDS,
      filters: [['agent', '=', agentName]],
      limit: 1000,
    });
    return triggers.map(mapAgentTriggerListItem);
  } catch (error) {
    console.error(`Error fetching triggers for agent ${agentName}:`, error);
    throw error;
  }
}

/**
 * Create a new agent document
 */
export async function createAgent(data: Partial<AgentDoc>): Promise<AgentDoc> {
  try {
    // Frappe JS SDK uses createDoc method
    const newAgent = await db.createDoc(doctype.Agent, data);
    return newAgent as AgentDoc;
  } catch (error) {
    console.error('Error creating agent:', error);
    throw error;
  }
}

/**
 * Update an agent document
 */
export async function updateAgent(name: string, data: Partial<AgentDoc>): Promise<AgentDoc> {
  try {
    await db.updateDoc(doctype.Agent, name, data);
    // Fetch updated document to return
    const updatedAgent = await db.getDoc(doctype.Agent, name);
    return updatedAgent as AgentDoc;
  } catch (error) {
    console.error(`Error updating agent ${name}:`, error);
    throw error;
  }
}
