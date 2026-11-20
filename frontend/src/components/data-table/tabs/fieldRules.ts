import type { DataTableFieldDef, TableToolSignature } from '@/types/dataTable.types';

/** Plain-words rules for one field: "Required, Unique, Hidden, Read only". */
export function fieldRulesText(f: DataTableFieldDef): string {
	const rules: string[] = [];
	if (f.reqd) rules.push('Required');
	if (f.unique) rules.push('Unique');
	if (f.hidden) rules.push('Hidden');
	if (f.read_only) rules.push('Read only');
	return rules.length ? rules.join(', ') : 'No rules';
}

/** "What the agent sees" for a field, taken from the create tool's params when available. */
export function agentSeesText(f: DataTableFieldDef, signature: TableToolSignature | null): string {
	const tools = signature?.tools ?? [];
	for (const t of tools) {
		const p = t.params.find((x) => x.name === f.fieldname);
		if (p) {
			const kind = p.required ? 'required' : 'optional';
			return `${f.fieldname}: ${p.type}, ${kind}${p.description ? `. ${p.description}` : ''}`;
		}
	}
	if (f.hidden) return 'Not shown to agents';
	return `${f.fieldname}${f.description ? `. ${f.description}` : ''}`;
}
