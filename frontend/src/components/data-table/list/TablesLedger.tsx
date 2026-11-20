import { ArrowRight, Table2, Trash2, KeyRound } from 'lucide-react';
import { OverflowMenu, ResourceList, ResourceRow } from '@/components/patterns';
import { formatTimeAgo } from '@/utils/time';
import { agentAccessText, type TableRowModel } from './tableListModel';

export interface TablesLedgerProps {
	rows: TableRowModel[];
	legacy?: boolean;
	onOpen: (row: TableRowModel) => void;
	onAgentAccess: (row: TableRowModel) => void;
	onDelete: (row: TableRowModel) => void;
}

/** The Tables ledger (mockup state 1): name + description, agent access, size, updated. */
export function TablesLedger({ rows, legacy, onOpen, onAgentAccess, onDelete }: TablesLedgerProps) {
	return (
		<ResourceList label="Tables" columns={[
				{ key: 'name', label: 'Table', width: 'minmax(0,2.2fr)' },
				{ key: 'access', label: 'Agent access', width: 'minmax(0,1.4fr)' },
				{ key: 'rows', label: 'Rows', width: '6rem', align: 'end' },
				{ key: 'fields', label: 'Fields', width: '6rem', align: 'end' },
				{ key: 'updated', label: 'Updated', width: '7rem', align: 'end' },
			]}
		>
			{rows.map((r) => (
				<ResourceRow
					key={r.id}
					glyph={<Table2 aria-hidden="true" className="h-4 w-4 shrink-0 text-steel-soft" />}
					title={r.name}
					reason={r.description || undefined}
					cells={{
						access: agentAccessText(r, legacy),
						rows: <span className="text-meta text-steel">{r.rows.toLocaleString()}</span>,
						fields: <span className="text-meta text-steel">{r.fields.toLocaleString()}</span>,
						updated: r.modified ? formatTimeAgo(r.modified) : '',
					}}
					onOpen={() => onOpen(r)}
					actions={
						<OverflowMenu
							size="icon-sm"
							label={`More actions for ${r.name}`}
							items={[
								{ label: 'Open', icon: ArrowRight, onSelect: () => onOpen(r) },
								{ label: 'Agent access', icon: KeyRound, onSelect: () => onAgentAccess(r) },
								{ label: 'Delete', icon: Trash2, destructive: true, separated: true, onSelect: () => onDelete(r) },
							]}
						/>
					}
				/>
			))}
		</ResourceList>
	);
}
