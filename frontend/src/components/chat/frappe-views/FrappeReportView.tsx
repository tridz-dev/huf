/**
 * Renders a frappe-report artifact payload (see
 * huf/ai/tools/frappe_generic.py::handle_render_frappe_view, mode="report")
 * as a table (same shape as FrappeListView) with a filter bar above it: one
 * simple input per filterable field from `meta.fields`.
 *
 * Like FrappeListView's pager, `onFilterChange` is a stub - it reports the
 * filters the user typed, wiring them to an actual tool re-invocation and
 * refetch is a follow-up.
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ArrowUpDown, Filter } from 'lucide-react';
import type { FrappeFieldMeta, FrappeViewPayload } from '@/types/artifact.types';
import { formatFrappeCellValue, isDisplayField } from './frappeFieldFormat';

export interface FrappeReportViewProps {
	payload: FrappeViewPayload;
	/** Called with the full filter map whenever a filter input changes.
	 * Actually re-running the query against the backend tool is a
	 * follow-up - this component only tracks and reports filter state. */
	onFilterChange?: (filters: Record<string, string>) => void;
}

export function FrappeReportView({ payload, onFilterChange }: FrappeReportViewProps) {
	const rows = useMemo(
		() => (Array.isArray(payload.data) ? payload.data : [payload.data]),
		[payload.data]
	);

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

	const updateFilter = (fieldname: string, value: string) => {
		setFilters((prev) => {
			const next = { ...prev, [fieldname]: value };
			onFilterChange?.(next);
			return next;
		});
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

	return (
		<div className="space-y-3">
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
			<div className="text-xs text-steel-soft">
				{payload.total_count ?? rows.length} record(s)
			</div>
		</div>
	);
}

export default FrappeReportView;
