import { call } from '@/lib/frappe-sdk';

/** How many agents use each source (rows in the Agent Knowledge child table, grouped). */
export async function getAgentCountsBySource(): Promise<Record<string, number>> {
  const res = (await call.get('frappe.client.get_list', {
    doctype: 'Agent Knowledge',
    parent: 'Agent',
    fields: JSON.stringify(['knowledge_source', { COUNT: '*', as: 'count' }]),
    group_by: 'knowledge_source',
    limit_page_length: 5000,
  })) as { message?: Array<{ knowledge_source: string; count: number | string }> };
  const out: Record<string, number> = {};
  for (const r of res.message ?? []) out[r.knowledge_source] = Number(r.count) || 0;
  return out;
}
