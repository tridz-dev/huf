/**
 * Knowledge Source and Knowledge Input configuration constants.
 * Centralised so select options can be updated in one place.
 */

export const knowledgeTypes = [
	{ label: 'SQLite FTS', value: 'sqlite_fts' },
	{ label: 'SQLite Vec', value: 'sqlite_vec' },
	{ label: 'ChromaDB', value: 'chroma' },
	{ label: 'PGVector', value: 'pgvector' },
	{ label: 'zvec (Embedded)', value: 'zvec' },
	{ label: 'Redis', value: 'redis' },

] as const;

export type KnowledgeTypeOption = (typeof knowledgeTypes)[number]['value'];

export const VECTOR_KNOWLEDGE_TYPES = ['sqlite_vec', 'chroma', 'pgvector', 'redis', 'zvec'] as const;


export function isVectorKnowledgeType(type: string): boolean {
	return (VECTOR_KNOWLEDGE_TYPES as readonly string[]).includes(type);
}

export const knowledgeTypeLabels: Record<string, string> = {
	sqlite_fts: 'FTS',
	sqlite_vec: 'Vec',
	chroma: 'Chroma',
	pgvector: 'PGVector',
	zvec: 'zvec',
	redis: 'Redis',

};

export const chromaModes = [
	{ label: 'File', value: 'File' },
	{ label: 'Server', value: 'Server' },
] as const;

export type ChromaModeOption = (typeof chromaModes)[number]['value'];

export const knowledgeScopes = [
	{ label: 'Site', value: 'Site' },
	{ label: 'Workspace', value: 'Workspace' },
	{ label: 'Agent', value: 'Agent' },
	{ label: 'Global', value: 'Global' },
] as const;

export type KnowledgeScopeOption = (typeof knowledgeScopes)[number]['value'];

export const knowledgeSourceStatuses = [
	{ label: 'Pending', value: 'Pending' },
	{ label: 'Indexing', value: 'Indexing' },
	{ label: 'Ready', value: 'Ready' },
	{ label: 'Error', value: 'Error' },
	{ label: 'Rebuilding', value: 'Rebuilding' },
] as const;

export type KnowledgeSourceStatusOption = (typeof knowledgeSourceStatuses)[number]['value'];

export const knowledgeStorageModes = [
	{ label: 'Frappe File', value: 'Frappe File' },
] as const;

export type KnowledgeStorageModeOption = (typeof knowledgeStorageModes)[number]['value'];

export const knowledgeInputTypes = [
	{ label: 'File', value: 'File' },
	{ label: 'Text', value: 'Text' },
	{ label: 'URL', value: 'URL' },
] as const;

export type KnowledgeInputTypeOption = (typeof knowledgeInputTypes)[number]['value'];

export const knowledgeInputStatuses = [
	{ label: 'Pending', value: 'Pending' },
	{ label: 'Processing', value: 'Processing' },
	{ label: 'Indexed', value: 'Indexed' },
	{ label: 'Error', value: 'Error' },
] as const;

export type KnowledgeInputStatusOption = (typeof knowledgeInputStatuses)[number]['value'];

/**
 * Mode options for Agent Knowledge child table (how the knowledge source is used).
 */
export const knowledgeModes = [
	{ label: 'Mandatory', value: 'Mandatory' },
	{ label: 'Optional', value: 'Optional' },
] as const;

export type KnowledgeModeOption = (typeof knowledgeModes)[number]['value'];

/**
 * Status filter options for the Knowledge Sources listing page.
 * Includes an "All" option plus source-level statuses and disabled.
 */
export const knowledgeSourceFilterStatuses = [
	{ label: 'All status', value: 'all' },
	{ label: 'Ready', value: 'ready' },
	{ label: 'Pending', value: 'pending' },
	{ label: 'Indexing', value: 'indexing' },
	{ label: 'Error', value: 'error' },
	{ label: 'Disabled', value: 'disabled' },
] as const;
