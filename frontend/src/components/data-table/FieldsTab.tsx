import type { DataTableSchema } from '@/types/dataTable.types';

export interface FieldsTabProps {
	schema: DataTableSchema;
	tableId: string;
	onChanged: () => void;
}

/** Fields tab (stub; implemented by task TB-5). */
export function FieldsTab({ schema }: FieldsTabProps) {
	return <div>{schema.fields.length} fields</div>;
}
