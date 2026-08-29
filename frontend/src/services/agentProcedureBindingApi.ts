import type { Filter } from 'frappe-js-sdk/lib/db/types';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';

export type AgentProcedureBindingHealth = 'Unknown' | 'Healthy' | 'Degraded' | 'Unhealthy';

export interface AgentProcedureBindingDoc {
  name: string;
  agent: string;
  procedure: string;
  procedure_id?: string;
  version?: number;
  enabled?: 0 | 1;
  priority?: number;
  fallback_enabled?: 0 | 1;
  health?: AgentProcedureBindingHealth;
  creation?: string;
  modified?: string;
}

const LIST_FIELDS = [
  'name',
  'agent',
  'procedure',
  'procedure_id',
  'version',
  'enabled',
  'priority',
  'fallback_enabled',
  'health',
  'creation',
];

/** All `Agent Procedure Binding` rows for one Agent, newest first. */
export async function getAgentProcedureBindings(agent: string): Promise<AgentProcedureBindingDoc[]> {
  if (!agent) return [];
  try {
    return (await db.getDocList(doctype['Agent Procedure Binding'], {
      fields: LIST_FIELDS,
      filters: [['agent', '=', agent]] as Filter<Record<string, unknown>>[],
      orderBy: { field: 'priority', order: 'asc' },
      limit: 200,
    })) as AgentProcedureBindingDoc[];
  } catch (error) {
    handleFrappeError(error, `Error fetching procedure bindings for ${agent}`);
    return [];
  }
}

export interface CreateAgentProcedureBindingInput {
  agent: string;
  procedure: string;
  enabled?: boolean;
  priority?: number;
  fallback_enabled?: boolean;
}

export async function createAgentProcedureBinding(
  input: CreateAgentProcedureBindingInput
): Promise<AgentProcedureBindingDoc | undefined> {
  try {
    const doc = await db.createDoc(doctype['Agent Procedure Binding'], {
      agent: input.agent,
      procedure: input.procedure,
      enabled: input.enabled === false ? 0 : 1,
      priority: input.priority ?? 0,
      fallback_enabled: input.fallback_enabled ? 1 : 0,
    });
    return doc as AgentProcedureBindingDoc;
  } catch (error) {
    handleFrappeError(error, 'Error creating procedure binding');
    throw error;
  }
}

export async function updateAgentProcedureBinding(
  name: string,
  data: Partial<Pick<AgentProcedureBindingDoc, 'enabled' | 'priority' | 'fallback_enabled'>>
): Promise<AgentProcedureBindingDoc | undefined> {
  try {
    return (await db.updateDoc(doctype['Agent Procedure Binding'], name, data)) as unknown as AgentProcedureBindingDoc;
  } catch (error) {
    handleFrappeError(error, `Error updating procedure binding ${name}`);
    throw error;
  }
}

export async function deleteAgentProcedureBinding(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['Agent Procedure Binding'], name);
  } catch (error) {
    handleFrappeError(error, `Error deleting procedure binding ${name}`);
    throw error;
  }
}
