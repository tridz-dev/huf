import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus, Pencil, Trash2, Loader2, Database, RefreshCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { DataRecordList } from '@/components/data-table/DataRecordList';
import { DataRecordForm } from '@/components/data-table/DataRecordForm';
import { DeleteTableDialog } from '@/components/data-table/DeleteTableDialog';
import {
	getTableSchema,
	getTableRecords,
	deleteDataTable,
} from '@/services/dataTableApi';
import type { DataTableFieldDef, DataTableSchema } from '@/types/dataTable.types';

export function DataTableViewPage() {
	const { tableId } = useParams<{ tableId: string }>();
	const navigate = useNavigate();

	const [schema, setSchema] = useState<DataTableSchema | null>(null);
	const [records, setRecords] = useState<Record<string, unknown>[]>([]);
	const [loading, setLoading] = useState(true);
	const [recordsLoading, setRecordsLoading] = useState(true);
	const [search, setSearch] = useState('');
	const [hasMore, setHasMore] = useState(false);
	const [page, setPage] = useState(0);

	const [formOpen, setFormOpen] = useState(false);
	const [editRecord, setEditRecord] = useState<Record<string, unknown> | null>(null);
	const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
	const [deleting, setDeleting] = useState(false);

	const loadSchema = useCallback(async () => {
		if (!tableId) return;
		try {
			const s = await getTableSchema(tableId);
			setSchema(s);
		} catch (err: any) {
			toast.error('Failed to load table', { description: err.message });
			navigate('/data');
		} finally {
			setLoading(false);
		}
	}, [tableId, navigate]);

	const loadRecords = useCallback(
		async (reset = false) => {
			if (!schema) return;
			setRecordsLoading(true);
			try {
				const start = reset ? 0 : page * 20;
				const result = await getTableRecords(schema.doctype_name, {
					limit: 20,
					start,
				});
				if (reset) {
					setRecords(result.items);
					setPage(1);
				} else {
					setRecords((prev) => [...prev, ...result.items]);
					setPage((p) => p + 1);
				}
				setHasMore(result.hasMore);
			} catch (err: any) {
				toast.error('Failed to load records', { description: err.message });
			} finally {
				setRecordsLoading(false);
			}
		},
		[schema, page]
	);

	useEffect(() => {
		loadSchema();
	}, [loadSchema]);

	useEffect(() => {
		if (schema) {
			setPage(0);
			setRecords([]);
			loadRecords(true);
		}
		// Only reload when schema changes
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [schema?.name]);

	const handleRecordSaved = () => {
		loadRecords(true);
	};

	const handleRowClick = (record: Record<string, unknown>) => {
		setEditRecord(record);
		setFormOpen(true);
	};

	const handleAddRecord = () => {
		setEditRecord(null);
		setFormOpen(true);
	};

	const handleDeleteTable = async () => {
		if (!tableId) return;
		setDeleting(true);
		try {
			const result = await deleteDataTable(tableId);
			toast.success(
				`Table deleted (${result.deleted_records} record${result.deleted_records !== 1 ? 's' : ''} removed)`
			);
			navigate('/data');
		} catch (err: any) {
			toast.error('Failed to delete table', { description: err.message });
		} finally {
			setDeleting(false);
			setDeleteDialogOpen(false);
		}
	};

	if (loading || !schema) {
		return (
			<div className="flex items-center justify-center h-full">
				<Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
			</div>
		);
	}

	const dataFields = schema.fields.filter(
		(f: DataTableFieldDef) =>
			f.fieldtype !== 'Section Break' && f.fieldtype !== 'Column Break'
	);
	const recordCount = records.length;

	return (
		<div className="h-full overflow-auto">
			<div className="p-6 space-y-6">
				{/* Header */}
				<div className="flex items-start justify-between gap-4">
					<div>
						<h2 className="text-xl font-semibold">{schema.table_name}</h2>
						{schema.description && (
							<p className="text-sm text-muted-foreground mt-1">
								{schema.description}
							</p>
						)}
						<div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
							<span>{dataFields.length} fields</span>
							<span>{recordCount} records loaded</span>
						</div>
					</div>
					<div className="flex items-center gap-2 shrink-0">
						<Button
							variant="outline"
							size="sm"
							onClick={() => navigate(`/data/${tableId}/edit`)}
						>
							<Pencil className="w-3.5 h-3.5 mr-1.5" />
							Edit Table
						</Button>
						<Button
							variant="outline"
							size="sm"
							onClick={() => setDeleteDialogOpen(true)}
							className="text-destructive hover:text-destructive"
						>
							<Trash2 className="w-3.5 h-3.5 mr-1.5" />
							Delete
						</Button>
						<Button size="sm" onClick={handleAddRecord}>
							<Plus className="w-3.5 h-3.5 mr-1.5" />
							Add Record
						</Button>
					</div>
				</div>

				{/* Search + Refresh */}
				<div className="flex items-center gap-4">
					<div className="flex-1">
						<Input
							placeholder="Search records..."
							value={search}
							onChange={(e) => setSearch(e.target.value)}
							className="h-8 text-sm max-w-sm"
						/>
					</div>
					<Button
						variant="ghost"
						size="icon"
						className="h-8 w-8"
						onClick={() => loadRecords(true)}
					>
						<RefreshCcw className="w-3.5 h-3.5" />
					</Button>
				</div>

				{/* Records table */}
				{records.length === 0 && !recordsLoading ? (
					<div className="flex flex-col items-center justify-center py-16 border border-dashed rounded-lg">
						<Database className="w-10 h-10 text-muted-foreground mb-3" />
						<p className="text-sm text-muted-foreground mb-3">
							No records in this table yet
						</p>
						<Button size="sm" onClick={handleAddRecord}>
							<Plus className="w-3.5 h-3.5 mr-1.5" />
							Add First Record
						</Button>
					</div>
				) : (
					<DataRecordList
						records={records}
						fields={schema.fields}
						loading={recordsLoading && records.length === 0}
						onRowClick={handleRowClick}
					/>
				)}

				{/* Load More */}
				{hasMore && (
					<div className="text-center">
						<Button
							variant="outline"
							size="sm"
							onClick={() => loadRecords(false)}
							disabled={recordsLoading}
						>
							{recordsLoading ? (
								<Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
							) : null}
							Load More
						</Button>
					</div>
				)}
			</div>

			{/* Record Form Sheet */}
			<DataRecordForm
				open={formOpen}
				onOpenChange={setFormOpen}
				doctypeName={schema.doctype_name}
				fields={schema.fields}
				record={editRecord}
				onSaved={handleRecordSaved}
			/>

			{/* Delete Table Dialog */}
			<DeleteTableDialog
				open={deleteDialogOpen}
				onOpenChange={setDeleteDialogOpen}
				tableName={schema.table_name}
				recordCount={recordCount}
				onConfirm={handleDeleteTable}
				loading={deleting}
			/>
		</div>
	);
}
