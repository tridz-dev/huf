import { useCallback, useEffect, useState } from 'react';
import { getDataTables, getTableAgentAccessCounts } from '@/services/dataTableApi';
import { listTablesSummary } from '@/services/dataTables/rowsApi';
import { fromLegacy, fromSummary, type TableRowModel } from './tableListModel';

export interface TablesListState {
	rows: TableRowModel[];
	loading: boolean;
	error: string | null;
	/** True when the backend lacks list_tables_summary and agent names are unavailable. */
	legacy: boolean;
	reload: () => Promise<void>;
}

/** listTablesSummary(), falling back to getDataTables + agent counts on older backends. */
export function useTablesList(): TablesListState {
	const [rows, setRows] = useState<TableRowModel[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [legacy, setLegacy] = useState(false);

	const reload = useCallback(async () => {
		setLoading(true);
		setError(null);
		try {
			setRows((await listTablesSummary()).map(fromSummary));
			setLegacy(false);
		} catch {
			try {
				const [list, counts] = await Promise.all([getDataTables({ limit: 500 }), getTableAgentAccessCounts()]);
				setRows(list.items.map((t) => fromLegacy(t, counts[t.name] ?? 0)));
				setLegacy(true);
			} catch (e) {
				setError(e instanceof Error ? e.message : 'Could not load tables.');
			}
		} finally {
			setLoading(false);
		}
	}, []);

	useEffect(() => {
		void reload();
	}, [reload]);

	return { rows, loading, error, legacy, reload };
}
