import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Pencil } from 'lucide-react';
import { OverflowMenu, ResourceList, ResourceRow } from '@/components/patterns';
import { friendlyTypeName, typeGlyph } from '@/data/fieldTypeLabels';
import { getTableToolSignature } from '@/services/dataTableApi';
import type { DataTableSchema, TableToolSignature } from '@/types/dataTable.types';
import { agentSeesText, fieldRulesText } from './tabs/fieldRules';

export interface FieldsTabProps {
	schema: DataTableSchema;
	tableId: string;
	onChanged: () => void;
}

const LAYOUT = new Set(['Tab Break', 'Section Break', 'Column Break']);

/** Fields tab: the table's fields in order, with rules and what agents see. */
export function FieldsTab({ schema, tableId }: FieldsTabProps) {
	const navigate = useNavigate();
	const [sig, setSig] = useState<TableToolSignature | null>(null);

	useEffect(() => {
		let live = true;
		getTableToolSignature(tableId).then(
			(s) => live && setSig(s),
			() => {},
		);
		return () => {
			live = false;
		};
	}, [tableId]);

	const fields = schema.fields.filter((f) => !LAYOUT.has(f.fieldtype));
	const edit = () => navigate(`/data/${tableId}/edit`);

	return (
		<div className="space-y-3">
			<p className="text-ui-text text-steel">
				These are the columns of {schema.table_name}. Agents use the same fields you see here.
			</p>
			<ResourceList label="Fields" columns={['Field', 'Rules', 'What the agent sees', '']}>
				{fields.map((f) => {
					const Glyph = typeGlyph(f.fieldtype);
					return (
						<ResourceRow
							key={f.fieldname}
							glyph={<Glyph aria-hidden="true" className="h-4 w-4 shrink-0 text-steel" />}
							title={f.label || f.fieldname}
							reason={friendlyTypeName(f.fieldtype)}
							origin={fieldRulesText(f)}
							status={<span className="text-meta text-steel-soft">{agentSeesText(f, sig)}</span>}
							actions={
								<OverflowMenu
									size="icon-sm"
									label={`More actions for ${f.label || f.fieldname}`}
									items={[{ label: 'Edit in builder', icon: Pencil, onSelect: edit }]}
								/>
							}
						/>
					);
				})}
			</ResourceList>
		</div>
	);
}
