import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Download, Loader2, Pencil, Plus, Trash2, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { OverflowMenu, type OverflowMenuItem } from '@/components/patterns';
import { PageFrame } from '@/layouts/PageFrame';
import { DeleteTableDialog } from '@/components/data-table/DeleteTableDialog';
import { FieldsTab } from '@/components/data-table/FieldsTab';
import { AgentsTab } from '@/components/data-table/AgentsTab';
import { ImportDialog } from '@/components/data-table/import/ImportDialog';
import { DataTab, type DataTabHandle } from '@/components/data-table/view/DataTab';
import { ActivityTab } from '@/components/data-table/view/ActivityTab';
import { dataFields, errorText } from '@/components/data-table/view/model';
import { deleteDataTable, getTableSchema } from '@/services/dataTableApi';
import type { DataTableSchema } from '@/types/dataTable.types';

export const TABLE_TABS = ['data', 'fields', 'agents', 'activity'] as const;
export type TableTab = (typeof TABLE_TABS)[number];
const TAB_LABEL: Record<TableTab, string> = { data: 'Data', fields: 'Fields', agents: 'Agents', activity: 'Activity' };

export function parseTableTab(v: string | null): TableTab {
	return (TABLE_TABS as readonly string[]).includes(v ?? '') ? (v as TableTab) : 'data';
}

export function DataTableViewPage() {
	const { tableId } = useParams<{ tableId: string }>();
	const navigate = useNavigate();
	const [params, setParams] = useSearchParams();
	const tab = parseTableTab(params.get('tab'));
	const importOpen = params.get('import') === '1';

	const [schema, setSchema] = useState<DataTableSchema | null>(null);
	const [rowCount, setRowCount] = useState<number | undefined>(undefined);
	const [deleteOpen, setDeleteOpen] = useState(false);
	const [deleting, setDeleting] = useState(false);
	const [dataKey, setDataKey] = useState(0);
	const dataRef = useRef<DataTabHandle>(null);

	const loadSchema = useCallback(async () => {
		if (!tableId) return;
		try {
			setSchema(await getTableSchema(tableId));
		} catch (err) {
			toast.error('Failed to load table', { description: errorText(err) });
			navigate('/data');
		}
	}, [tableId, navigate]);

	useEffect(() => {
		void loadSchema();
	}, [loadSchema]);

	const update = (changes: Record<string, string | null>) => {
		const next = new URLSearchParams(params);
		for (const [k, v] of Object.entries(changes)) (v === null ? next.delete(k) : next.set(k, v));
		setParams(next, { replace: true });
	};
	const setTab = (t: TableTab) => update({ tab: t === 'data' ? null : t });

	const addRow = () => {
		if (tab !== 'data') setTab('data');
		window.setTimeout(() => dataRef.current?.addRow(), 0);
	};

	const handleDelete = async () => {
		if (!tableId) return;
		setDeleting(true);
		try {
			const result = await deleteDataTable(tableId);
			toast.success(`Table deleted (${result.deleted_records} ${result.deleted_records === 1 ? 'row' : 'rows'} removed)`);
			navigate('/data');
		} catch (err) {
			toast.error('Failed to delete table', { description: errorText(err) });
		} finally {
			setDeleting(false);
			setDeleteOpen(false);
		}
	};

	if (!schema || !tableId) {
		return (
			<div className="flex h-full items-center justify-center">
				<Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
			</div>
		);
	}

	const empty = rowCount === 0;
	const items: OverflowMenuItem[] = [
		...(tab === 'data'
			? [
					{ label: 'Export', icon: Download, onSelect: () => dataRef.current?.exportAll() },
					...(empty ? [] : [{ label: 'Import', icon: Upload, onSelect: () => update({ import: '1' }) }]),
				]
			: []),
		{ label: 'Edit fields', icon: Pencil, onSelect: () => setTab('fields') },
		{ label: 'Delete table', icon: Trash2, destructive: true, separated: true, onSelect: () => setDeleteOpen(true) },
	];

	const actions = (
		<>
			{tab === 'data' &&
				(empty ? (
					<Button size="sm" onClick={() => update({ import: '1' })}>
						<Upload aria-hidden="true" className="mr-1.5 h-3.5 w-3.5" />
						Import
					</Button>
				) : (
					<Button size="sm" onClick={addRow}>
						<Plus aria-hidden="true" className="mr-1.5 h-3.5 w-3.5" />
						Add row
					</Button>
				))}
			<OverflowMenu items={items} label={`More actions for ${schema.table_name}`} />
		</>
	);

	return (
		<PageFrame
			title={schema.table_name}
			meta={`${rowCount !== undefined ? `${rowCount.toLocaleString()} rows · ` : ''}${dataFields(schema).length} ${dataFields(schema).length === 1 ? 'field' : 'fields'}`}
			actions={actions}
			tabs={
				<Tabs value={tab} onValueChange={(v) => setTab(parseTableTab(v))}>
					<TabsList aria-label="Table sections">
						{TABLE_TABS.map((t) => (
							<TabsTrigger key={t} value={t}>
								{TAB_LABEL[t]}
							</TabsTrigger>
						))}
					</TabsList>
				</Tabs>
			}
		>
			{tab === 'data' && <DataTab key={dataKey} ref={dataRef} schema={schema} tableId={tableId} onImport={() => update({ import: '1' })} onCount={setRowCount} />}
			{tab === 'fields' && <FieldsTab schema={schema} tableId={tableId} onChanged={() => void loadSchema()} />}
			{tab === 'agents' && <AgentsTab schema={schema} tableId={tableId} />}
			{tab === 'activity' && <ActivityTab tableId={tableId} />}

			<DeleteTableDialog
				open={deleteOpen}
				onOpenChange={setDeleteOpen}
				tableName={schema.table_name}
				tableId={schema.name}
				recordCount={rowCount ?? 0}
				onConfirm={handleDelete}
				loading={deleting}
			/>
			<ImportDialog
				open={importOpen}
				onOpenChange={(o) => !o && update({ import: null })}
				schema={schema}
				onSchemaChanged={loadSchema}
				onImported={() => {
					update({ import: null, tab: null });
					void loadSchema();
					setDataKey((k) => k + 1);
				}}
			/>
		</PageFrame>
	);
}
