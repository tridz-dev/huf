import { useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useState } from 'react';
import { Bot, Database, Settings, Table2, Trash2, Pencil } from 'lucide-react';
import { TABLE_ICON_MAP } from '@/data/tableIcons';
import {
	PageLayout,
	FilterBar,
	GridView,
	ItemCard,
	LoadMoreButton,
} from '../components/dashboard';
import { DeleteTableDialog } from '../components/data-table/DeleteTableDialog';
import { TableAgentAccessModal } from '../components/data-table/TableAgentAccessModal';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getDataTables, deleteDataTable, getTableAgentAccessCounts } from '../services/dataTableApi';
import { formatTimeAgo } from '../utils/time';
import type { HufDataTable } from '../types/dataTable.types';

export { DataPage };
export default DataPage;

function DataPage() {
	const navigate = useNavigate();
	const [deleteTable, setDeleteTable] = useState<HufDataTable | null>(null);
	const [deleting, setDeleting] = useState(false);
	const [accessTable, setAccessTable] = useState<HufDataTable | null>(null);
	const [agentCounts, setAgentCounts] = useState<Record<string, number>>({});

	// "N agents" badge counts, keyed by table doctype (one bulk fetch, not per card)
	const loadAgentCounts = useCallback(async () => {
		const counts = await getTableAgentAccessCounts();
		setAgentCounts(counts);
	}, []);

	useEffect(() => {
		loadAgentCounts();
	}, [loadAgentCounts]);

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
		<PageLayout
			subtitle="Create and manage custom data tables"
			filters={
				<FilterBar
					searchPlaceholder="Search tables..."
					searchValue={search}
					onSearchChange={setSearch}
				/>
			}
		>
			<GridView
				items={tables}
				columns={{ sm: 1, md: 2, lg: 3 }}
				loading={initialLoading}
				emptyState={
					<div className="text-center py-12">
						<Database className="w-12 h-12 text-steel-soft mx-auto mb-4" />
						<p className="font-body text-steel-soft mb-2">No data tables yet</p>
						<p className="text-sm text-steel">
							Create your first table to start managing structured data.
						</p>
					</div>
				}
				renderItem={(table) => {
					const agentCount = agentCounts[table.doctype_name] ?? 0;
					return (
						<ItemCard
							title={table.table_name}
							description={table.description || 'No description'}
							icon={table.icon ? TABLE_ICON_MAP[table.icon] ?? Table2 : Table2}
							status={
								table.is_active
									? { label: 'Active', variant: 'success' }
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
							badges={
								agentCount > 0
									? [
											{
												label: `${agentCount} agent${agentCount > 1 ? 's' : ''}`,
												variant: 'secondary',
											},
										]
									: []
							}
							menuIcon={Settings}
							menuActions={[
								{
									icon: Pencil,
									label: 'Edit Table',
									onClick: () => navigate(`/data/${table.name}/edit`),
								},
								{
									icon: Bot,
									label: 'Add to agent…',
									onClick: () => setAccessTable(table),
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
					);
				}}
				keyExtractor={(table) => table.name}
			/>
			<LoadMoreButton
				hasMore={hasMore}
				loading={loadingMore}
				onLoadMore={loadMore}
				disabled={!!search || initialLoading}
			/>
			{!hasMore && tables.length > 0 && (
				<div className="text-center py-4 text-sm font-body text-steel">
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
			<TableAgentAccessModal
				open={!!accessTable}
				onOpenChange={(open) => !open && setAccessTable(null)}
				table={accessTable}
				onSaved={loadAgentCounts}
			/>
		</PageLayout>
	);
}
