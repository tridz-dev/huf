import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { KnowledgeSourceDoc } from '@/types/agent.types';
import { handleFrappeError } from '@/lib/frappe-error';

const KNOWLEDGE_SOURCE_FIELDS = [
	'name',
	'source_name',
	'status',
	'description',
	'knowledge_type',
	'total_chunks',
	'last_indexed_at',
	'disabled',
];

/**
 * Fetch all knowledge sources (for source picker)
 */
export async function getKnowledgeSources(): Promise<KnowledgeSourceDoc[]> {
	try {
		const sources = await db.getDocList(doctype['Knowledge Source'], {
			fields: KNOWLEDGE_SOURCE_FIELDS,
			filters: [['disabled', '=', 0]] as any,
			limit: 1000,
			orderBy: { field: 'source_name', order: 'asc' },
		});
		return sources as KnowledgeSourceDoc[];
	} catch (error) {
		handleFrappeError(error, 'Error fetching knowledge sources');
		return [];
	}
}

/**
 * Fetch knowledge source details for given names (used when loading an agent)
 */
export async function getKnowledgeSourcesByNames(names: string[]): Promise<KnowledgeSourceDoc[]> {
	if (!names.length) return [];
	try {
		const sources = await db.getDocList(doctype['Knowledge Source'], {
			fields: KNOWLEDGE_SOURCE_FIELDS,
			filters: [['name', 'in', names]] as any,
			limit: 1000,
		});
		return sources as KnowledgeSourceDoc[];
	} catch (error) {
		handleFrappeError(error, 'Error fetching knowledge sources');
		return [];
	}
}
