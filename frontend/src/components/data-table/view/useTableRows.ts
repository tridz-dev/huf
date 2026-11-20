import { useCallback, useEffect, useRef, useState } from 'react';
import type { GridColumn } from '@/components/grid';
import { getTableRecords } from '@/services/dataTableApi';
import type { TableRecordFilter } from '@/types/dataTable.types';
import { PAGE_SIZE, errorText, toRow, type Row } from './model';

export interface RowsQuery {
	doctype: string;
	columns: GridColumn<Row>[];
	search: string;
	filters: TableRecordFilter[];
	sort: { field: string; order: 'asc' | 'desc' } | null;
	page: number;
}

/** One page of rows for the current query. `total` is undefined on older backends. */
export function useTableRows(q: RowsQuery) {
	const [rows, setRows] = useState<Row[]>([]);
	const [total, setTotal] = useState<number | undefined>(undefined);
	const [hasMore, setHasMore] = useState(false);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const seq = useRef(0);
	const key = JSON.stringify([q.doctype, q.search, q.filters, q.sort, q.page]);
	const latest = useRef(q);
	latest.current = q;

	const reload = useCallback(async () => {
		const cur = latest.current;
		const id = ++seq.current;
		setLoading(true);
		try {
			const r = await getTableRecords(cur.doctype, {
				limit: PAGE_SIZE,
				start: cur.page * PAGE_SIZE,
				search: cur.search || undefined,
				filters: cur.filters.length ? cur.filters : undefined,
				orderBy: cur.sort ?? undefined,
			});
			if (id !== seq.current) return;
			setRows(r.items.map((it) => toRow(it, cur.columns)));
			setTotal(r.total);
			setHasMore(r.hasMore);
			setError(null);
		} catch (err) {
			if (id === seq.current) setError(errorText(err, 'Could not load rows'));
		} finally {
			if (id === seq.current) setLoading(false);
		}
	}, []);

	useEffect(() => {
		void reload();
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [key]);

	return { rows, setRows, total, hasMore, loading, error, reload };
}
