import { useState } from 'react';
import {
	ColumnDef,
	flexRender,
	getCoreRowModel,
	getSortedRowModel,
	getFilteredRowModel,
	SortingState,
	VisibilityState,
	useReactTable,
} from '@tanstack/react-table';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Settings2, Filter } from 'lucide-react';

interface DataListViewProps<TData, TValue> {
	columns: ColumnDef<TData, TValue>[];
	data: TData[];
	loading?: boolean;
	emptyState?: React.ReactNode;
	onRowClick?: (row: TData) => void;
}

export function DataListView<TData, TValue>({
	columns,
	data,
	loading,
	emptyState,
	onRowClick,
}: DataListViewProps<TData, TValue>) {
	const [sorting, setSorting] = useState<SortingState>([]);
	const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
	const [globalFilter, setGlobalFilter] = useState('');

	const table = useReactTable({
		data,
		columns,
		getCoreRowModel: getCoreRowModel(),
		getSortedRowModel: getSortedRowModel(),
		getFilteredRowModel: getFilteredRowModel(),
		onSortingChange: setSorting,
		onColumnVisibilityChange: setColumnVisibility,
		onGlobalFilterChange: setGlobalFilter,
		state: {
			sorting,
			columnVisibility,
			globalFilter,
		},
	});

	return (
		<div className="space-y-4">
			<div className="flex items-center justify-between">
				<div className="flex items-center space-x-2">
                    <div className="relative">
                        <Filter className="absolute left-2 top-2.5 h-3.5 w-3.5 text-steel" />
					    <Input
						    placeholder="Filter columns locally..."
						    value={globalFilter ?? ''}
						    onChange={(e) => setGlobalFilter(e.target.value)}
						    className="h-8 w-[200px] pl-8 rounded-none border-line bg-panel text-ink"
					    />
                    </div>
				</div>
				<div className="flex items-center space-x-2">
                    <span className="text-xs text-steel-soft mr-2">
                        {table.getFilteredRowModel().rows.length} record(s) visible
                    </span>
					<DropdownMenu>
						<DropdownMenuTrigger asChild>
							<Button variant="outline" size="sm" className="hidden h-8 lg:flex rounded-none border-line text-steel hover:bg-paper-deep">
								<Settings2 className="mr-2 h-4 w-4" />
								Columns
							</Button>
						</DropdownMenuTrigger>
						<DropdownMenuContent align="end" className="w-[150px] rounded-none border-line bg-panel">
							{table
								.getAllColumns()
								.filter((column) => typeof column.accessorFn !== 'undefined' && column.getCanHide())
								.map((column) => {
									return (
										<DropdownMenuCheckboxItem
											key={column.id}
											className="capitalize rounded-none text-ink hover:bg-paper-deep focus:bg-paper-deep cursor-pointer"
											checked={column.getIsVisible()}
											onCheckedChange={(value) => column.toggleVisibility(!!value)}
										>
											{column.id}
										</DropdownMenuCheckboxItem>
									);
								})}
						</DropdownMenuContent>
					</DropdownMenu>
				</div>
			</div>
			<div className="rounded-none border border-line bg-panel">
				<Table>
					<TableHeader>
						{table.getHeaderGroups().map((headerGroup) => (
							<TableRow key={headerGroup.id} className="border-line hover:bg-transparent">
								{headerGroup.headers.map((header) => {
									return (
										<TableHead key={header.id} className="text-steel">
											{header.isPlaceholder
												? null
												: flexRender(header.column.columnDef.header, header.getContext())}
										</TableHead>
									);
								})}
							</TableRow>
						))}
					</TableHeader>
					<TableBody>
						{loading ? (
							<TableRow className="border-line hover:bg-transparent">
								<TableCell colSpan={columns.length} className="h-24 text-center">
									<div className="space-y-2">
										{[...Array(5)].map((_, i) => (
											<div key={i} className="h-12 bg-line rounded-none animate-pulse" />
										))}
									</div>
								</TableCell>
							</TableRow>
						) : table.getRowModel().rows?.length ? (
							table.getRowModel().rows.map((row) => (
								<TableRow
									key={row.id}
									data-state={row.getIsSelected() && 'selected'}
									className={`border-line transition-colors hover:bg-paper-deep ${onRowClick ? 'cursor-pointer' : ''}`}
									onClick={() => onRowClick?.(row.original)}
								>
									{row.getVisibleCells().map((cell) => (
										<TableCell key={cell.id} className="text-ink">
											{flexRender(cell.column.columnDef.cell, cell.getContext())}
										</TableCell>
									))}
								</TableRow>
							))
						) : (
							<TableRow className="border-line hover:bg-transparent">
								<TableCell colSpan={columns.length} className="h-24 text-center text-steel">
									{emptyState || 'No results.'}
								</TableCell>
							</TableRow>
						)}
					</TableBody>
				</Table>
			</div>
		</div>
	);
}
