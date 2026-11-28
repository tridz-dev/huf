import { useResourceAccess } from '@/hooks/permissions/useResourceAccess';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PageFrame } from '@/layouts/PageFrame';
import { AskField, FilterPills, StatusSentence } from '@/components/patterns';
import { ConfirmDestructive, type Dependent } from '@/components/grid';
import { AppTablesSection } from '../components/data-table/AppTablesSection';
import { CreateTableDialog, type TableStart } from '../components/data-table/list/CreateTableDialog';
import { EmptyTables } from '../components/data-table/list/EmptyTables';
import { TablesLedger } from '../components/data-table/list/TablesLedger';
import { useTablesList } from '../components/data-table/list/useTablesList';
import {
	ALL_GROUPS,
	NO_AGENT,
	UNGROUPED,
	filterRows,
	type TableRowModel,
} from '../components/data-table/list/tableListModel';
import { createDataTable, deleteDataTable } from '../services/dataTableApi';
import { getTableDependencies } from '../services/dataTables/rowsApi';

export { DataPage };
export default DataPage;

function DataPage() {
	const navigate = useNavigate();
	const access = useResourceAccess('dataTable');
	const { rows, loading, error, legacy, reload } = useTablesList();
	const [search, setSearch] = useState('');
	const [group, setGroup] = useState(ALL_GROUPS);
	const [createOpen, setCreateOpen] = useState(false);
	const [createStart, setCreateStart] = useState<TableStart>('blank');
	const [toDelete, setToDelete] = useState<TableRowModel | null>(null);
	const [dependents, setDependents] = useState<Dependent[]>([]);

	useEffect(() => {
		if (error) toast.error('Could not load tables', { description: error });
	}, [error]);

	const pills = useMemo(() => {
		const groups = Array.from(new Set(rows.map((r) => r.group))).sort((a, b) =>
			a === UNGROUPED ? 1 : b === UNGROUPED ? -1 : a.localeCompare(b)
		);
		const showGroups = groups.length > 1 || (groups.length === 1 && groups[0] !== UNGROUPED);
		return [
			{ value: ALL_GROUPS, label: 'All', count: rows.length },
			...(showGroups ? groups.map((g) => ({ value: g, label: g, count: rows.filter((r) => r.group === g).length })) : []),
			{ value: NO_AGENT, label: 'Used by no agent', count: rows.filter((r) => r.agents.length === 0).length },
		];
	}, [rows]);

	const visible = useMemo(() => filterRows(rows, group, search), [rows, group, search]);
	const usedByAgents = rows.filter((r) => r.agents.length > 0).length;

	const openCreate = (start: TableStart = 'blank') => {
		setCreateStart(start);
		setCreateOpen(true);
	};

	const handleCreate = async ({ name, description, start }: { name: string; description: string; start: TableStart }) => {
		const created = await createDataTable({
			table_name: name,
			description: description || undefined,
			fields: [{ fieldname: 'name_text', fieldtype: 'Data', label: 'Name', in_list_view: 1 }],
		});
		setCreateOpen(false);
		const suffix = start === 'csv' ? '?import=1' : start === 'paste' ? '?paste=1' : '';
		navigate(`/data/${created.name}${suffix}`);
	};

	const askDelete = async (row: TableRowModel) => {
		setToDelete(row);
		setDependents(row.agents.map((a) => ({ kind: 'Agent', label: a.agent_name })));
		try {
			const deps = await getTableDependencies(row.id);
			setDependents([
				...deps.agents.map((a) => ({ kind: 'Agent', label: a.agent_name })),
				...deps.flows.map((f) => ({ kind: 'Flow', label: f.title })),
			]);
		} catch {
			// Older backend: keep the agent list we already have from the summary.
		}
	};

	const confirmDelete = async () => {
		if (!toDelete) return;
		try {
			await deleteDataTable(toDelete.id);
			toast.success(`Deleted ${toDelete.name}`);
			await reload();
		} catch (err) {
			toast.error('Could not delete the table', { description: err instanceof Error ? err.message : undefined });
			throw err;
		}
	};

	const empty = !loading && rows.length === 0 && !error;

	return (
		<PageFrame
			title="Tables"
			actions={access.canCreate ? (
				<div className="flex items-center gap-2">
					<Button variant="outline" onClick={() => openCreate('csv')}>
						<Upload className="h-4 w-4" />
						Import
					</Button>
					<Button onClick={() => openCreate('blank')}>New table</Button>
				</div>
			) : undefined}
		>
			<div className="space-y-4 px-6 pb-6">
				{empty ? (
					access.canCreate ? (
						<EmptyTables onStart={openCreate} onNew={() => openCreate('blank')} />
					) : (
						<p className="py-8 text-center text-ui-text text-steel">{access.isLoading ? 'Loading tables' : 'There are no tables yet.'}</p>
					)
				) : (
					<>
						<AskField value={search} onChange={setSearch} placeholder="Search tables" />
						<FilterPills label="Filter tables" pills={pills} value={group} onChange={setGroup} />
						<StatusSentence
							tone={usedByAgents > 0 ? 'ready' : 'off'}
							parts={[
								loading ? 'Loading tables' : `${rows.length} ${rows.length === 1 ? 'table' : 'tables'}`,
								!loading && `used by agents: ${usedByAgents}`,
							]}
						/>
						{!loading && visible.length === 0 ? (
							<p className="py-8 text-center text-ui-text text-steel">
								No tables match.{' '}
								<button
									type="button"
									className="text-signal-ink underline-offset-4 hover:underline"
									onClick={() => {
										setSearch('');
										setGroup(ALL_GROUPS);
									}}
								>
									Clear filters
								</button>
							</p>
						) : (
							<TablesLedger
								rows={visible}
								legacy={legacy}
								onOpen={(r) => navigate(`/data/${r.id}`)}
								onAgentAccess={(r) => navigate(`/data/${r.id}?tab=agents`)}
								onDelete={access.canDelete ? (r) => void askDelete(r) : undefined}
							/>
						)}
					</>
				)}
				<AppTablesSection />
			</div>

			<CreateTableDialog
				key={`${createOpen}-${createStart}`}
				open={createOpen}
				onOpenChange={setCreateOpen}
				existingNames={rows.map((r) => r.name)}
				initialStart={createStart}
				onCreate={handleCreate}
			/>
			<ConfirmDestructive
				open={!!toDelete}
				onOpenChange={(o) => !o && setToDelete(null)}
				title={`Delete ${toDelete?.name ?? 'table'}?`}
				consequence={
					toDelete
						? `Removes all ${toDelete.rows.toLocaleString()} ${toDelete.rows === 1 ? 'row' : 'rows'} and ${toDelete.fields} ${toDelete.fields === 1 ? 'field' : 'fields'}.`
						: ''
				}
				recovery="This can't be undone."
				dependents={dependents}
				confirmText={toDelete?.name}
				actionLabel="Delete table"
				onConfirm={confirmDelete}
			/>
		</PageFrame>
	);
}
