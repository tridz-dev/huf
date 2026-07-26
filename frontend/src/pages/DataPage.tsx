import { useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useState } from 'react';
import { Database, Settings, Table2, Trash2, Pencil, Layers, List } from 'lucide-react';
import { TABLE_ICON_MAP } from '@/data/tableIcons';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import {
	PageLayout,
	FilterBar,
	GridView,
	ItemCard,
	LoadMoreButton,
} from '../components/dashboard';
import { DeleteTableDialog } from '../components/data-table/DeleteTableDialog';
import { TableAgentAccessModal } from '../components/data-table/TableAgentAccessModal';
import { AppTablesSection } from '../components/data-table/AppTablesSection';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getDataTables, deleteDataTable, getTableAgentAccessCounts } from '../services/dataTableApi';
import { formatTimeAgo } from '../utils/time';
import type { HufDataTable } from '../types/dataTable.types';

/** Below this table count, default to the flat view so grouping doesn't add clutter for a
 * handful of tables. Users can still toggle either way explicitly. */
const AUTO_FLAT_THRESHOLD = 3;

export { DataPage };
export default DataPage;

function DataPage() {
	const navigate = useNavigate();
	const [deleteTable, setDeleteTable] = useState<HufDataTable | null>(null);
	const [deleting, setDeleting] = useState(false);
	const [viewModeOverride, setViewModeOverride] = useState<'flat' | 'grouped' | null>(null);
	const [accessTable, setAccessTable] = useState<HufDataTable | null>(null);
	const [agentAccessCounts, setAgentAccessCounts] = useState<Record<string, number>>({});

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

	const loadAgentCounts = async () => {
		setAgentAccessCounts(await getTableAgentAccessCounts());
	};

	useEffect(() => {
		void loadAgentCounts();
	}, []);

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
		} catch (err) {
			toast.error('Failed to delete table', { description: err instanceof Error ? err.message : 'An error occurred.' });
		} finally {
			setDeleting(false);
		}
	};

	const groupedTables = tables.reduce((acc, table) => {
		const groupName = table.table_group || 'Ungrouped';
		if (!acc[groupName]) acc[groupName] = [];
		acc[groupName].push(table);
		return acc;
	}, {} as Record<string, HufDataTable[]>);

	const groupNames = Object.keys(groupedTables).sort((a, b) => {
		if (a === 'Ungrouped') return 1;
		if (b === 'Ungrouped') return -1;
		return a.localeCompare(b);
	});

	const hasAnyGroups = groupNames.some((name) => name !== 'Ungrouped');
	const viewMode =
		viewModeOverride ?? (tables.length <= AUTO_FLAT_THRESHOLD ? 'flat' : 'grouped');

	const renderCard = useMemo(
		() => (table: HufDataTable) => (
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
					{
						label: 'Agents',
						value: (agentAccessCounts[table.name] ?? 0).toString(),
						icon: Settings,
					},
					{ label: 'Modified', value: formatTimeAgo(table.modified) },
				]}
				menuIcon={Settings}
				menuActions={[
					{
						icon: Settings,
						label: 'Agent Access',
						onClick: () => setAccessTable(table),
					},
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
		),
		[navigate, agentAccessCounts]
	);

	return (
		<PageLayout
			subtitle="Create and manage custom data tables"
			filters={
				<div className="flex items-center gap-2">
					<FilterBar
						searchPlaceholder="Search tables..."
						searchValue={search}
						onSearchChange={setSearch}
					/>
					{hasAnyGroups && (
						<ToggleGroup
							type="single"
							value={viewMode}
							onValueChange={(value) => value && setViewModeOverride(value as 'flat' | 'grouped')}
							className="rounded-none border border-line"
						>
							<ToggleGroupItem value="flat" aria-label="Simple view" className="rounded-none" title="Simple view">
								<List className="w-4 h-4" />
							</ToggleGroupItem>
							<ToggleGroupItem value="grouped" aria-label="Grouped view" className="rounded-none" title="Grouped view">
								<Layers className="w-4 h-4" />
							</ToggleGroupItem>
						</ToggleGroup>
					)}
				</div>
			}
		>
			{groupNames.length === 0 ? (
				<GridView
					items={[]}
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
					renderItem={() => <></>}
					keyExtractor={() => ''}
				/>
			) : viewMode === 'flat' ? (
				<GridView
					items={tables}
					columns={{ sm: 1, md: 2, lg: 3 }}
					loading={initialLoading}
					renderItem={renderCard}
					keyExtractor={(table) => table.name}
				/>
			) : (
				<div className="space-y-4">
					{groupNames.map((groupName) => (
						<div key={groupName}>
							<h2 className="text-lg font-medium text-ink mb-4 mt-8 first:mt-0">
								{groupName}
							</h2>
							<GridView
								items={groupedTables[groupName]}
								columns={{ sm: 1, md: 2, lg: 3 }}
								loading={initialLoading}
								renderItem={renderCard}
								keyExtractor={(table) => table.name}
							/>
						</div>
					))}
				</div>
			)}
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

			<AppTablesSection />

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
