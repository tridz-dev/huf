/**
 * Renders a frappe-report artifact payload (see
 * huf/ai/tools/frappe_generic.py::handle_render_frappe_view, mode="report")
 * as a table (same shape as FrappeListView) with a filter bar above it: one
 * simple input per filterable field from `meta.fields`.
 *
 * Filter edits re-fetch through `frappe.client.get_list` (via frappe-js-sdk's
 * `db.getDocList`, debounced) the same way FrappeListView's pager does - see
 * that file's header comment for why this goes through the framework's own
 * whitelisted list method rather than back through the agent/tool layer.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ArrowUpDown, Filter, ExternalLink, Loader2 } from 'lucide-react';
import { db, call } from '@/lib/frappe-sdk';
import type { FrappeFieldMeta, FrappeViewPayload } from '@/types/artifact.types';
import { formatFrappeCellValue, isDisplayField } from './frappeFieldFormat';
import { deskListUrl } from './frappeDeskUrl';

export interface FrappeReportViewProps {
	payload: FrappeViewPayload;
}

export function FrappeReportView({ payload }: FrappeReportViewProps) {
	const [rows, setRows] = useState<Record<string, unknown>[]>(() =>
		Array.isArray(payload.data) ? payload.data : [payload.data]
	);
	const [totalCount, setTotalCount] = useState(payload.total_count ?? rows.length);
	const [loading, setLoading] = useState(false);
	const [fetchError, setFetchError] = useState<string | null>(null);
	const debounceRef = useRef<ReturnType<typeof setTimeout>>();

	const displayFields = useMemo<FrappeFieldMeta[]>(() => {
		const metaFields = payload.meta?.fields ?? [];
		const requested = payload.fields;
		const byName = new Map(metaFields.map((f) => [f.fieldname, f]));
		const base = requested?.length
			? requested.map((name) => byName.get(name)).filter((f): f is FrappeFieldMeta => Boolean(f))
			: metaFields.filter(isDisplayField);
		return base.slice(0, 8);
	}, [payload.meta, payload.fields]);

	const [filters, setFilters] = useState<Record<string, string>>({});

	const runQuery = async (nextFilters: Record<string, string>) => {
		setLoading(true);
		setFetchError(null);
		try {
			const fieldNames = displayFields.map((f) => f.fieldname);
			const activeFilters = Object.entries(nextFilters)
				.filter(([, value]) => value.trim() !== '')
				.map(([fieldname, value]) => [fieldname, 'like', `%${value}%`] as [string, 'like', string]);
			const result = await db.getDocList(payload.doctype, {
				fields: fieldNames.length ? fieldNames : undefined,
				filters: activeFilters.length ? (activeFilters as never) : undefined,
				limit: payload.limit_page_length ?? 100,
			});
			setRows(result as unknown as Record<string, unknown>[]);
			const countResponse = await call.get('frappe.client.get_count', {
				doctype: payload.doctype,
				...(activeFilters.length ? { filters: JSON.stringify(activeFilters) } : {}),
			});
			const count = Number(countResponse?.message);
			if (!Number.isNaN(count)) setTotalCount(count);
		} catch (error) {
			console.error('Failed to re-run Frappe report query:', error);
			setFetchError('Could not apply filters - showing the last loaded data.');
		} finally {
			setLoading(false);
		}
	};

	const updateFilter = (fieldname: string, value: string) => {
		setFilters((prev) => {
			const next = { ...prev, [fieldname]: value };
			if (debounceRef.current) clearTimeout(debounceRef.current);
			debounceRef.current = setTimeout(() => runQuery(next), 400);
			return next;
		});
	};

	useEffect(() => {
		return () => {
			if (debounceRef.current) clearTimeout(debounceRef.current);
		};
	}, []);

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

	return (
		<div className="space-y-3">
			<div className="flex justify-end">
				{/* TODO(frappe-views): this artifact mode is not backed by a real
				 * Frappe Report/Query Report entity - handle_render_frappe_view's
				 * mode="report" branch is just handle_list_records against
				 * payload.doctype with different pagination defaults, and the
				 * payload carries no report name to route /app/query-report/<name>
				 * to. erpnext_reports.py's handle_list_reports (a separate tool)
				 * returns report names but no report_type, and isn't wired into
				 * this payload either, so we can't disambiguate Query Report vs.
				 * Report Builder here. Linking to the underlying doctype's Desk
				 * list view instead, same as list mode - see PLAN.md's Phase 4
				 * finding for the full writeup. */}
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
			<div className="rounded-lg border border-line bg-panel p-3">
				<div className="flex items-center gap-1.5 mb-2 text-xs text-steel">
					<Filter className="h-3.5 w-3.5" />
					Filters
				</div>
				<div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
					{displayFields.map((field) => (
						<div key={field.fieldname} className="space-y-1">
							<Label htmlFor={`filter-${field.fieldname}`} className="text-[11px] text-steel-soft">
								{field.label || field.fieldname}
							</Label>
							<Input
								id={`filter-${field.fieldname}`}
								size="sm"
								value={filters[field.fieldname] ?? ''}
								onChange={(e) => updateFilter(field.fieldname, e.target.value)}
								placeholder="Any"
							/>
						</div>
					))}
				</div>
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
			<div className="flex items-center gap-2 text-xs text-steel-soft">
				{loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
				<span>{totalCount} record(s)</span>
				{fetchError && <span className="text-destructive">{fetchError}</span>}
			</div>
		</div>
	);
}

export default FrappeReportView;
