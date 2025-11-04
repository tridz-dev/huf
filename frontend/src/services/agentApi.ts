import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { AgentDoc } from '@/types/agent.types';

/**
 * Fields needed for the agents list page
 */
const AGENT_LIST_FIELDS = [
  'name',
  'agent_name',
  'instructions',
  'model',
  'disabled',
  'last_run',
  'total_run',
];

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
