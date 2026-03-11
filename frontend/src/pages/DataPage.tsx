import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Database, Settings, Table2 } from 'lucide-react';
import {
	PageLayout,
	FilterBar,
	GridView,
	ItemCard,
	LoadMoreButton,
} from '../components/dashboard';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getDataTables } from '../services/dataTableApi';
import { formatTimeAgo } from '../utils/time';
import type { HufDataTable } from '../types/dataTable.types';

export { DataPage };
export default DataPage;

function DataPage() {
	const navigate = useNavigate();

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
						menuActions={[
							{
								icon: Settings,
								label: 'Edit Table',
								onClick: () => navigate(`/data/${table.name}/edit`),
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
		</PageLayout>
	);
}
