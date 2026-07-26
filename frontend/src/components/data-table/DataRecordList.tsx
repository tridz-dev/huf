import { useMemo, useState } from 'react';
import {
	type ColumnDef,
	flexRender,
	getCoreRowModel,
	getSortedRowModel,
	type SortingState,
	useReactTable,
} from '@tanstack/react-table';
import { ArrowUpDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { formatTimeAgo } from '@/utils/time';
import type { DataTableFieldDef } from '@/types/dataTable.types';

interface DataRecordListProps {
	records: Record<string, unknown>[];
	fields: DataTableFieldDef[];
	loading?: boolean;
	onRowClick?: (record: Record<string, unknown>) => void;
}

function formatCellValue(value: unknown, fieldtype: string): React.ReactNode {
	if (value === null || value === undefined || value === '') {
		return <span className="text-muted-foreground">-</span>;
	}

	switch (fieldtype) {
		case 'Check':
			return (
				<Badge variant={value ? 'default' : 'secondary'}>
					{value ? 'Yes' : 'No'}
				</Badge>
			);
		case 'Currency':
			return typeof value === 'number' ? value.toFixed(2) : String(value);
		case 'Percent':
			return `${value}%`;
		case 'Color':
			return (
				<div className="flex items-center gap-2">
					<div
						className="w-4 h-4 rounded border"
						style={{ backgroundColor: String(value) }}
					/>
					<span className="text-xs">{String(value)}</span>
				</div>
			);
		case 'Rating': {
			const rating = Number(value);
			const stars = Math.round(rating * 5);
			return <span className="text-xs">{'★'.repeat(stars)}{'☆'.repeat(5 - stars)}</span>;
		}
		default:
			return String(value);
	}
}

export function DataRecordList({
	records,
	fields,
	loading,
	onRowClick,
}: DataRecordListProps) {
	const [sorting, setSorting] = useState<SortingState>([]);

	const listFields = useMemo(() => {
		const visible = fields.filter(
			(f) =>
				f.in_list_view === 1 &&
				f.fieldtype !== 'Section Break' &&
				f.fieldtype !== 'Column Break'
		);
		if (visible.length > 0) return visible;
		return fields
			.filter((f) => f.fieldtype !== 'Section Break' && f.fieldtype !== 'Column Break')
			.slice(0, 4);
	}, [fields]);

	const columns = useMemo<ColumnDef<Record<string, unknown>>[]>(() => {
		const cols: ColumnDef<Record<string, unknown>>[] = [
			{
				accessorKey: 'name',
				header: ({ column }) => (
					<Button
						variant="ghost"
						onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
						className="h-8 px-2 text-xs"
					>
						ID
						<ArrowUpDown className="ml-1 h-3 w-3" />
					</Button>
				),
				cell: ({ row }) => (
					<span className="text-xs font-mono text-muted-foreground">
						{String(row.getValue('name')).slice(0, 10)}
					</span>
				),
			},
		];

		for (const field of listFields) {
			cols.push({
				accessorKey: field.fieldname,
				header: ({ column }) => (
					<Button
						variant="ghost"
						onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
						className="h-8 px-2 text-xs"
					>
						{field.label}
						<ArrowUpDown className="ml-1 h-3 w-3" />
					</Button>
				),
				cell: ({ row }) =>
					<div className="text-sm max-w-48 truncate">
						{formatCellValue(row.getValue(field.fieldname), field.fieldtype)}
					</div>,
			});
		}

		cols.push({
			accessorKey: 'modified',
			header: ({ column }) => (
				<Button
					variant="ghost"
					onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
					className="h-8 px-2 text-xs"
				>
					Modified
					<ArrowUpDown className="ml-1 h-3 w-3" />
				</Button>
			),
			cell: ({ row }) => (
				<span className="text-xs text-muted-foreground">
					{formatTimeAgo(row.getValue('modified') as string)}
				</span>
			),
		});

		return cols;
	}, [listFields]);

	const table = useReactTable({
		data: records,
		columns,
		getCoreRowModel: getCoreRowModel(),
		getSortedRowModel: getSortedRowModel(),
		onSortingChange: setSorting,
		state: { sorting },
	});

	if (loading) {
		return (
			<div className="space-y-2">
				{[...Array(5)].map((_, i) => (
					<div key={i} className="h-12 bg-muted/50 rounded animate-pulse" />
				))}
			</div>
		);
	}

	return (
		<div className="overflow-hidden rounded-md border">
			<Table>
				<TableHeader>
					{table.getHeaderGroups().map((headerGroup) => (
						<TableRow key={headerGroup.id}>
							{headerGroup.headers.map((header) => (
								<TableHead key={header.id}>
									{header.isPlaceholder
										? null
										: flexRender(
												header.column.columnDef.header,
												header.getContext()
											)}
								</TableHead>
							))}
						</TableRow>
					))}
				</TableHeader>
				<TableBody>
					{table.getRowModel().rows?.length ? (
						table.getRowModel().rows.map((row) => (
							<TableRow
								key={row.id}
								className="cursor-pointer hover:bg-muted/50"
								onClick={() => onRowClick?.(row.original)}
							>
								{row.getVisibleCells().map((cell) => (
									<TableCell key={cell.id} className="py-2">
										{flexRender(cell.column.columnDef.cell, cell.getContext())}
									</TableCell>
								))}
							</TableRow>
						))
					) : (
						<TableRow>
							<TableCell colSpan={columns.length} className="h-24 text-center">
								<p className="text-muted-foreground">No records found</p>
							</TableCell>
						</TableRow>
					)}
				</TableBody>
			</Table>
		</div>
	);
}
