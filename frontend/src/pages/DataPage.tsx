import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useState } from 'react';
import { Database, Settings, Table2, Trash2, Pencil } from 'lucide-react';
import { TABLE_ICON_MAP } from '@/data/tableIcons';
import {
	FilterBar,
	GridView,
	ItemCard,
	LoadMoreButton,
} from '../components/dashboard';
import { DeleteTableDialog } from '../components/data-table/DeleteTableDialog';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getDataTables, deleteDataTable } from '../services/dataTableApi';
import { formatTimeAgo } from '../utils/time';
import type { HufDataTable } from '../types/dataTable.types';

export { DataPage };
export default DataPage;

function DataPage() {
	const navigate = useNavigate();
	const [deleteTable, setDeleteTable] = useState<HufDataTable | null>(null);
	const [deleting, setDeleting] = useState(false);

	const {
		items: tables,
		hasMore,
		initialLoading,
		loadingMore,
		search,
		setSearch,
		loadMore,
		total,
		error,
	} = useInfiniteScroll<{ page?: number; limit?: number; start?: number; search?: string }, HufDataTable>({
		fetchFn: async (params) => {
			const response = await getDataTables({
				page: params.page,
				limit: params.limit,
				start: params.start,
				search: params.search,
			});

			return {
				data: response.items,
				hasMore: response.hasMore,
				total: response.total,
			};
		},
		initialParams: {},
		pageSize: 20,
		debounceMs: 300,
		autoLoad: true,
	});

	useEffect(() => {
		if (error) {
			toast.error('Failed to load data tables', {
				description: error.message || 'An error occurred.',
				duration: 5000,
			});
		}
	}, [error]);

	const handleDeleteConfirm = async () => {
		if (!deleteTable) return;
		setDeleting(true);
		try {
			const result = await deleteDataTable(deleteTable.name);
			toast.success(
				`Table deleted (${result.deleted_records} record${result.deleted_records !== 1 ? 's' : ''} removed)`
			);
			setDeleteTable(null);
			// Reload the page to refresh the list since we removed a table
			window.location.reload();
		} catch (err: any) {
			toast.error('Failed to delete table', { description: err.message });
		} finally {
			setDeleting(false);
		}
	};

	return (
		<div className="flex flex-col h-full overflow-hidden p-6 gap-6">
			<div className="flex-none">
				<div className="mb-4">
					<h1 className="text-2xl font-semibold tracking-tight">Data Tables</h1>
					<p className="text-sm text-muted-foreground mt-1">Create and manage custom data tables</p>
				</div>
				<FilterBar
					searchPlaceholder="Search tables..."
					searchValue={search}
					onSearchChange={setSearch}
				/>
			</div>

			<div className="flex-1 overflow-auto">
				<GridView
					items={tables}
					columns={{ sm: 1, md: 2, lg: 3 }}
					loading={initialLoading}
					emptyState={
						<div className="text-center py-12">
							<Database className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
							<p className="text-muted-foreground mb-2">No data tables yet</p>
							<p className="text-sm text-muted-foreground">
								Create your first table to start managing structured data.
							</p>
						</div>
					}
					renderItem={(table) => (
						<ItemCard
							title={table.table_name}
							description={table.description || 'No description'}
							icon={table.icon ? TABLE_ICON_MAP[table.icon] ?? Table2 : Table2}
							status={
								table.is_active
									? { label: 'Active', variant: 'default' }
									: { label: 'Inactive', variant: 'secondary' }
							}
							metadata={[
								{ label: 'Fields', value: table.field_count?.toString() || '0', icon: Table2 },
								{
									label: 'Records',
									value: table.record_count?.toString() || '0',
									icon: Database,
								},
								{ label: 'Modified', value: formatTimeAgo(table.modified) },
							]}
							menuIcon={Settings}
							menuActions={[
								{
									icon: Pencil,
									label: 'Edit Table',
									onClick: () => navigate(`/data/${table.name}/edit`),
								},
								{
									icon: Trash2,
									label: 'Delete Table',
									variant: 'destructive',
									onClick: () => setDeleteTable(table),
								},
							]}
							onClick={() => navigate(`/data/${table.name}`)}
						/>
					)}
					keyExtractor={(table) => table.name}
				/>
				<LoadMoreButton
					hasMore={hasMore}
					loading={loadingMore}
					onLoadMore={loadMore}
					disabled={!!search || initialLoading}
				/>
				{!hasMore && tables.length > 0 && (
					<div className="text-center py-4 text-sm text-muted-foreground">
						{total !== undefined
							? `Showing all ${total} tables`
							: 'No more tables to load'}
					</div>
				)}

				<DeleteTableDialog
					open={!!deleteTable}
					onOpenChange={(open) => !open && setDeleteTable(null)}
					tableName={deleteTable?.table_name || ''}
					recordCount={deleteTable?.record_count || 0}
					onConfirm={handleDeleteConfirm}
					loading={deleting}
				/>
			</div>
		</div>
	);
}
