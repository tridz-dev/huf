import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';

/** Input counts for every source at once, grouped by source and status. */
export async function getKnowledgeInputCountsBySource(): Promise<
  Array<{ knowledge_source: string; status: string; count: number }>
> {
  const rows = await db.getDocList(doctype['Knowledge Input'], {
    fields: ['knowledge_source', 'status', { COUNT: '*', as: 'count' }] as never,
    groupBy: 'knowledge_source, status',
    limit: 5000,
  } as never);
  return (rows as unknown as Array<{ knowledge_source: string; status: string; count: number | string }>).map((r) => ({
    knowledge_source: r.knowledge_source,
    status: r.status,
    count: Number(r.count) || 0,
  }));
}
