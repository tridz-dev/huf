import type { HufDataTable, TableAgentAction, TableSummary, TableSummaryAgent } from '@/types/dataTable.types';

/** One ledger row: a summary from the backend, or a legacy row mapped onto the same shape. */
export interface TableRowModel {
	id: string;
	name: string;
	description: string;
	group: string;
	fields: number;
	rows: number;
	modified: string;
	agents: TableSummaryAgent[];
}

export const NO_AGENT = 'none';
export const ALL_GROUPS = 'all';
export const UNGROUPED = 'Ungrouped';
/** Frappe-safe name: starts alphanumeric, then letters, digits, space, underscore, hyphen; max 140. */
export const TABLE_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9 _-]{0,139}$/;

const ACTION_WORD: Record<TableAgentAction, string> = {
	view: 'read',
	create: 'create',
	edit: 'edit',
	delete: 'delete',
};

export function fromSummary(s: TableSummary): TableRowModel {
	return {
		id: s.name,
		name: s.table_name,
		description: s.description ?? '',
		group: s.table_group || UNGROUPED,
		fields: s.field_count ?? 0,
		rows: s.record_count ?? 0,
		modified: s.modified,
		agents: s.agents ?? [],
	};
}

/** Fallback for older backends: legacy list + per-table agent counts (names unknown). */
export function fromLegacy(t: HufDataTable, agentCount: number): TableRowModel {
	return {
		id: t.name,
		name: t.table_name,
		description: t.description ?? '',
		group: t.table_group || UNGROUPED,
		fields: t.field_count ?? 0,
		rows: t.record_count ?? 0,
		modified: t.modified,
		agents: Array.from({ length: agentCount }, (_, i) => ({
			agent: `legacy-${i}`,
			agent_name: `Agent ${i + 1}`,
			actions: [],
		})),
	};
}

/** "Billing agent: read, edit" · "Billing agent: read +2 more" · "Used by no agent". */
export function agentAccessText(row: TableRowModel, legacy = false): string {
	if (row.agents.length === 0) return 'Used by no agent';
	if (legacy) return `Used by ${row.agents.length} ${row.agents.length === 1 ? 'agent' : 'agents'}`;
	const [first, ...rest] = row.agents;
	const acts = first.actions.map((a) => ACTION_WORD[a] ?? a).join(', ');
	const head = acts ? `${first.agent_name}: ${acts}` : first.agent_name;
	return rest.length ? `${head} +${rest.length} more` : head;
}

export function isValidTableName(name: string): boolean {
	return TABLE_NAME_PATTERN.test(name);
}

export function nameError(name: string, existing: string[]): string | null {
	if (!name.trim()) return null;
	if (!isValidTableName(name)) {
		return 'Start with a letter or number. Use only letters, numbers, spaces, - and _ (up to 140).';
	}
	if (existing.some((n) => n.toLowerCase() === name.toLowerCase())) return 'A table with this name already exists.';
	return null;
}

export function filterRows(rows: TableRowModel[], group: string, search: string): TableRowModel[] {
	const q = search.trim().toLowerCase();
	return rows.filter((r) => {
		if (group === NO_AGENT && r.agents.length > 0) return false;
		if (group !== NO_AGENT && group !== ALL_GROUPS && r.group !== group) return false;
		return !q || r.name.toLowerCase().includes(q) || r.description.toLowerCase().includes(q);
	});
}
