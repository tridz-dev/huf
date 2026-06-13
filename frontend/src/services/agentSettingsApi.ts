import { db } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

const SETTING_DOCTYPE = 'Agent Settings';
const SETTING_NAME = 'Agent Settings';

export interface AgentSettingsDoc {
  name: string;
  default_provider?: string | null;
  default_model?: string | null;
  skill_destinations?: string | null;
  last_skill_scans?: string | null;
}

export async function getAgentSettings(): Promise<AgentSettingsDoc> {
  try {
    const doc = await db.getDoc(SETTING_DOCTYPE, SETTING_NAME);
    return doc as AgentSettingsDoc;
  } catch (error) {
    handleFrappeError(error, 'Error fetching Agent Settings');
  }
}

export async function updateAgentSettings(data: Partial<AgentSettingsDoc>): Promise<AgentSettingsDoc> {
  try {
    await db.updateDoc(SETTING_DOCTYPE, SETTING_NAME, data);
    const updated = await db.getDoc(SETTING_DOCTYPE, SETTING_NAME);
    return updated as AgentSettingsDoc;
  } catch (error) {
    handleFrappeError(error, 'Error saving Agent Settings');
  }
}
