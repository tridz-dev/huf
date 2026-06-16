import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';

export interface HufAppSummary {
  name: string;       // same as app_id
  app_id: string;
  label: string;
  description: string;
  icon: string;
  shell: 'chat' | 'dashboard' | 'list';
  agent: string;
  status: 'Active' | 'Disabled';
}

export interface HufAppManifest {
  app_id: string;
  label: string;
  description?: string;
  icon?: string;
  tables: Array<{
    table_name: string;
    description?: string;
    fields: Array<{
      fieldname: string;
      label: string;
      fieldtype: string;
      reqd?: number;
      in_list_view?: number;
      options?: string;
    }>;
  }>;
  agent: {
    agent_name: string;
    instructions: string;
    model?: string;
    provider?: string;
  };
  knowledge?: Array<{
    source_name: string;
    knowledge_type: string;
    inputs: Array<{ input_type: string; text?: string }>;
  }>;
  shell: 'chat' | 'dashboard' | 'list';
  nav: Array<{
    label: string;
    type?: 'collection' | 'chat';
    table?: string;
    view?: 'grid' | 'list' | 'table';
    filter?: Array<[string, string, string]>;
  }>;
  views: Array<{
    table: string;
    collection_layout: 'grid' | 'list' | 'table';
    card_variant: 'summary-first' | 'data-first';
    list_fields: string[];
    record_view: 'form' | 'view';
  }>;
}

export async function getHufApps(): Promise<HufAppSummary[]> {
  try {
    return await db.getDocList(doctype.HufApp, {
      fields: ['name', 'app_id', 'label', 'description', 'icon', 'shell', 'agent', 'status'],
      filters: [['status', '=', 'Active']],
      orderBy: { field: 'creation', order: 'desc' },
    }) as HufAppSummary[];
  } catch (e) {
    handleFrappeError(e, 'Failed to load apps');
    return [];
  }
}

export async function getHufApp(appId: string): Promise<HufAppManifest> {
  try {
    const result = await call.get('huf.ai.app_installer.get_huf_app', { app_id: appId });
    return result.message as HufAppManifest;
  } catch (e) {
    handleFrappeError(e, 'Failed to load app');
    throw e;
  }
}

export async function deleteHufApp(appId: string): Promise<void> {
  try {
    await call.delete('huf.ai.app_installer.delete_huf_app', { app_id: appId });
  } catch (e) {
    handleFrappeError(e, 'Failed to delete app');
    throw e;
  }
}
