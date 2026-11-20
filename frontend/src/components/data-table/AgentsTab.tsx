import type { DataTableSchema } from '@/types/dataTable.types';

export interface AgentsTabProps {
	schema: DataTableSchema;
	tableId: string;
}

/** Agents tab (stub; implemented by task TB-6). */
export function AgentsTab(_props: AgentsTabProps) {
	return <div>Agents</div>;
}
