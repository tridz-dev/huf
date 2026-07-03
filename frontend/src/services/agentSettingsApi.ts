import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';

export interface AgentSettingsDoc {
  default_provider?: string;
  default_model?: string;
}

export async function getAgentSettings(): Promise<AgentSettingsDoc | undefined> {
  try {
    return await db.getDoc(doctype['Agent Settings'], doctype['Agent Settings']);
  } catch (error) {
    handleFrappeError(error, 'Error fetching Agent Settings');
  }
}

export async function updateAgentSettings(data: AgentSettingsDoc): Promise<void> {
  try {
    await db.updateDoc(doctype['Agent Settings'], doctype['Agent Settings'], data);
  } catch (error) {
    handleFrappeError(error, 'Error updating Agent Settings');
    throw error;
  }
}
