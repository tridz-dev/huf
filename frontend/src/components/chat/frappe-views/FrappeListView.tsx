/**
 * Renders a frappe-list artifact payload (see
 * huf/ai/tools/frappe_generic.py::handle_render_frappe_view, mode="list") as
 * a paginated table, columns derived from `meta.fields`.
 *
 * Pagination here is a client-side stub: the artifact payload is a single
 * static snapshot (the backend does not round-trip limit_start/
 * limit_page_length into the payload for list mode - see the NOTE on
 * FrappeViewPayload), so `onPageChange` just reports the page the caller
 * asked for. Wiring it to actually re-invoke the tool and refresh `data` is
 * a follow-up.
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
import { ArrowUpDown, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react';
import type { FrappeFieldMeta, FrappeViewPayload } from '@/types/artifact.types';
import { formatFrappeCellValue, isDisplayField } from './frappeFieldFormat';
import { deskListUrl } from './frappeDeskUrl';

export interface FrappeListViewProps {
	payload: FrappeViewPayload;
	/** Called with the next limit_start when the pager is used. Wiring this
	 * to an actual refetch against the backend tool is a follow-up. */
	onPageChange?: (limitStart: number, limitPageLength: number) => void;
}

export function FrappeListView({ payload, onPageChange }: FrappeListViewProps) {
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

	const limitStart = payload.limit_start ?? 0;
	const limitPageLength = payload.limit_page_length ?? rows.length ?? 20;
	const totalCount = payload.total_count ?? rows.length;
	const hasPrev = limitStart > 0;
	const hasNext = limitStart + limitPageLength < totalCount;

	return (
		<div className="space-y-3">
			<div className="flex justify-end">
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
					<Button
						variant="outline"
						size="sm"
						disabled={!hasPrev}
						onClick={() => onPageChange?.(Math.max(0, limitStart - limitPageLength), limitPageLength)}
					>
						<ChevronLeft className="h-3.5 w-3.5" />
						Prev
					</Button>
					<Button
						variant="outline"
						size="sm"
						disabled={!hasNext}
						onClick={() => onPageChange?.(limitStart + limitPageLength, limitPageLength)}
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
