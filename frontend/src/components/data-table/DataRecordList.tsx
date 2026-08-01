import { useMemo } from 'react';
import { type ColumnDef } from '@tanstack/react-table';
import { DataListView } from '@/components/dashboard/DataListView';
import { ArrowUpDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { formatTimeAgo } from '@/utils/time';
import { LAYOUT_FIELD_TYPES } from '@/data/fieldTypes';
import type { DataTableFieldDef } from '@/types/dataTable.types';

interface DataRecordListProps {
	records: Record<string, unknown>[];
	fields: DataTableFieldDef[];
	loading?: boolean;
	onRowClick?: (record: Record<string, unknown>) => void;
}

function formatCellValue(value: unknown, fieldtype: string): React.ReactNode {
	if (value === null || value === undefined || value === '') {
		return <span className="text-steel">-</span>;
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
	
	const listFields = useMemo(() => {
		const visible = fields.filter(
			(f) => f.in_list_view === 1 && !LAYOUT_FIELD_TYPES.includes(f.fieldtype)
		);
		if (visible.length > 0) return visible;
		return fields
			.filter((f) => !LAYOUT_FIELD_TYPES.includes(f.fieldtype))
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
						className="h-8 px-2 text-xs rounded-none text-steel hover:text-ink hover:bg-paper-deep"
					>
						ID
						<ArrowUpDown className="ml-1 h-3 w-3" />
					</Button>
				),
				cell: ({ row }) => (
					<span className="text-xs font-mono text-steel">
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
						className="h-8 px-2 text-xs rounded-none text-steel hover:text-ink hover:bg-paper-deep"
					>
						{field.label}
						<ArrowUpDown className="ml-1 h-3 w-3" />
					</Button>
				),
				cell: ({ row }) =>
					<div className="text-sm max-w-48 truncate text-ink">
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
					className="h-8 px-2 text-xs rounded-none text-steel hover:text-ink hover:bg-paper-deep"
				>
					Modified
					<ArrowUpDown className="ml-1 h-3 w-3" />
				</Button>
			),
			cell: ({ row }) => (
				<span className="text-xs text-steel">
					{formatTimeAgo(row.getValue('modified') as string)}
				</span>
			),
		});

		return cols;
	}, [listFields]);

	return (
		<DataListView
			columns={columns}
			data={records}
			loading={loading}
			onRowClick={onRowClick}
			emptyState={<p className="text-steel">No records found</p>}
		/>
	);
}