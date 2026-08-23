/**
 * Renders a frappe-list artifact payload (see
 * huf/ai/tools/frappe_generic.py::handle_render_frappe_view, mode="list") as
 * a paginated table, columns derived from `meta.fields`.
 *
 * Pagination re-fetches through `frappe.client.get_list` directly (via
 * frappe-js-sdk's `db.getDocList`, the same whitelisted, permission-checked
 * REST method the rest of the frontend already uses for Frappe list data -
 * see dataTableApi.ts) rather than round-tripping through the agent/tool
 * layer, since the artifact snapshot doesn't carry enough context (agent,
 * conversation) to safely reinvoke a tool call from a plain page/filter
 * click. `frappe.client.get_list` applies the same permission-query
 * conditions our backend tool does, so this is not a permission relaxation.
 */

import { useMemo, useState } from 'react';
import {
	type ColumnDef,
	getCoreRowModel,
	getSortedRowModel,
	useReactTable,
	flexRender,
	type SortingState,
} from '@tanstack/react-table';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { ArrowUpDown, ChevronLeft, ChevronRight, ExternalLink, Loader2 } from 'lucide-react';
import { db, call } from '@/lib/frappe-sdk';
import type { FrappeFieldMeta, FrappeViewPayload } from '@/types/artifact.types';
import { formatFrappeCellValue, isDisplayField } from './frappeFieldFormat';
import { deskListUrl } from './frappeDeskUrl';

export interface FrappeListViewProps {
	payload: FrappeViewPayload;
}

export function FrappeListView({ payload }: FrappeListViewProps) {
	const [rows, setRows] = useState<Record<string, unknown>[]>(() =>
		Array.isArray(payload.data) ? payload.data : [payload.data]
	);
	const [limitStart, setLimitStart] = useState(payload.limit_start ?? 0);
	const [totalCount, setTotalCount] = useState(payload.total_count ?? rows.length);
	const [loading, setLoading] = useState(false);
	const [fetchError, setFetchError] = useState<string | null>(null);
	const limitPageLength = payload.limit_page_length ?? rows.length ?? 20;

	const displayFields = useMemo<FrappeFieldMeta[]>(() => {
		const metaFields = payload.meta?.fields ?? [];
		const requested = payload.fields;
		const byName = new Map(metaFields.map((f) => [f.fieldname, f]));
		const base = requested?.length
			? requested.map((name) => byName.get(name)).filter((f): f is FrappeFieldMeta => Boolean(f))
			: metaFields.filter(isDisplayField);
		return base.slice(0, 8);
	}, [payload.meta, payload.fields]);

	const fetchPage = async (nextLimitStart: number) => {
		setLoading(true);
		setFetchError(null);
		try {
			const fieldNames = displayFields.map((f) => f.fieldname);
			const result = await db.getDocList(payload.doctype, {
				fields: fieldNames.length ? fieldNames : undefined,
				filters: (payload.filters as never) ?? undefined,
				limit_start: nextLimitStart,
				limit: limitPageLength,
			});
			setRows(result as unknown as Record<string, unknown>[]);
			setLimitStart(nextLimitStart);
			const countResponse = await call.get('frappe.client.get_count', {
				doctype: payload.doctype,
				...(payload.filters ? { filters: JSON.stringify(payload.filters) } : {}),
			});
			const count = Number(countResponse?.message);
			if (!Number.isNaN(count)) setTotalCount(count);
		} catch (error) {
			console.error('Failed to fetch Frappe list page:', error);
			setFetchError('Could not load this page - showing the last loaded data.');
		} finally {
			setLoading(false);
		}
	};

	const columns = useMemo<ColumnDef<Record<string, unknown>>[]>(() => {
		return displayFields.map((field) => ({
			id: field.fieldname,
			accessorKey: field.fieldname,
			header: ({ column }) => (
				<Button
					variant="ghost"
					onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
					className="h-8 px-2 text-xs rounded text-steel hover:text-ink hover:bg-paper-deep"
				>
					{field.label || field.fieldname}
					<ArrowUpDown className="ml-1 h-3 w-3" />
				</Button>
			),
			cell: ({ row }) => (
				<span className="text-sm text-ink">
					{formatFrappeCellValue(row.getValue(field.fieldname), field)}
				</span>
			),
		}));
	}, [displayFields]);

	const [sorting, setSorting] = useState<SortingState>([]);
	const table = useReactTable({
		data: rows,
		columns,
		getCoreRowModel: getCoreRowModel(),
		getSortedRowModel: getSortedRowModel(),
		onSortingChange: setSorting,
		state: { sorting },
	});

	const hasPrev = limitStart > 0;
	const hasNext = limitStart + limitPageLength < totalCount;

	return (
		<div className="space-y-3">
			<div className="flex items-center justify-between">
				{fetchError ? <span className="text-xs text-destructive">{fetchError}</span> : <span />}
				<a
					href={deskListUrl(payload.doctype)}
					target="_blank"
					rel="noopener noreferrer"
					className="inline-flex items-center gap-1 text-xs text-steel hover:text-ink"
				>
					Open in Desk
					<ExternalLink className="h-3 w-3" />
				</a>
			</div>
			<div className="rounded-lg border border-line bg-panel overflow-x-auto">
				<Table>
					<TableHeader>
						{table.getHeaderGroups().map((headerGroup) => (
							<TableRow key={headerGroup.id} className="border-line hover:bg-transparent">
								{headerGroup.headers.map((header) => (
									<TableHead key={header.id} className="text-steel">
										{header.isPlaceholder
											? null
											: flexRender(header.column.columnDef.header, header.getContext())}
									</TableHead>
								))}
							</TableRow>
						))}
					</TableHeader>
					<TableBody>
						{table.getRowModel().rows.length ? (
							table.getRowModel().rows.map((row) => (
								<TableRow key={row.id} className="border-line hover:bg-paper-deep">
									{row.getVisibleCells().map((cell) => (
										<TableCell key={cell.id}>
											{flexRender(cell.column.columnDef.cell, cell.getContext())}
										</TableCell>
									))}
								</TableRow>
							))
						) : (
							<TableRow className="hover:bg-transparent">
								<TableCell colSpan={columns.length || 1} className="h-24 text-center text-steel">
									No records.
								</TableCell>
							</TableRow>
						)}
					</TableBody>
				</Table>
			</div>
			<div className="flex items-center justify-between text-xs text-steel-soft">
				<span>
					{totalCount > 0
						? `${limitStart + 1}-${Math.min(limitStart + limitPageLength, totalCount)} of ${totalCount}`
						: '0 records'}
				</span>
				<div className="flex items-center gap-2">
					{loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-steel" />}
					<Button
						variant="outline"
						size="sm"
						disabled={!hasPrev || loading}
						onClick={() => fetchPage(Math.max(0, limitStart - limitPageLength))}
					>
						<ChevronLeft className="h-3.5 w-3.5" />
						Prev
					</Button>
					<Button
						variant="outline"
						size="sm"
						disabled={!hasNext || loading}
						onClick={() => fetchPage(limitStart + limitPageLength)}
					>
						Next
						<ChevronRight className="h-3.5 w-3.5" />
					</Button>
				</div>
			</div>
		</div>
	);
}

export default FrappeListView;
