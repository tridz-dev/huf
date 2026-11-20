import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Database, Plus, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
	BulkActionBar, ConfirmDestructive, DataGrid, FieldsMenu, FilterBuilder, GridFooter, GridToolbar, MatchCount, SortChip, sortDirectionLabel,
	type CellValue, type FilterCondition, type GridSort,
} from '@/components/grid';
import { AutosaveStatus, type AutosaveState } from '@/components/builder';
import { AskField, DropZone } from '@/components/patterns';
import { createTableRecord, getTableRecords } from '@/services/dataTableApi';
import { restoreRows } from '@/services/dataTables/rowsApi';
import type { DataTableSchema } from '@/types/dataTable.types';
import { RecordPanel } from './RecordPanel';
import { SetValueDialog } from './SetValueDialog';
import {
	DRAFT_PREFIX, PAGE_SIZE, buildColumns, defaultsFor, downloadCsv, errorText, isBlank, isDraft, planPaste,
	requiredWithoutDefault, toApiFilters, toApiValues, toCsv, toTsv, type Row,
} from './model';
import { deleteMany, fetchNames, insertMany, serverExport, setOne, updateMany } from './rowOps';
import { useTableRows } from './useTableRows';

export interface DataTabHandle {
	addRow: () => void;
	exportAll: () => void;
}

export interface DataTabProps {
	schema: DataTableSchema;
	tableId: string;
	onImport: () => void;
	/** Total rows in the whole table (unfiltered), when the server reports it. */
	onCount?: (total: number | undefined) => void;
}

let draftSeq = 0;

export const DataTab = forwardRef<DataTabHandle, DataTabProps>(function DataTab({ schema, tableId, onImport, onCount }, ref) {
	const doctype = schema.doctype_name;
	const columns = useMemo(() => buildColumns(schema), [schema]);
	const labelOf = useCallback((key: string) => columns.find((c) => c.key === key)?.label ?? key, [columns]);

	const [searchText, setSearchText] = useState('');
	const [search, setSearch] = useState('');
	const [filters, setFilters] = useState<FilterCondition[]>([]);
	const [gridSort, setGridSort] = useState<GridSort | null>(null);
	const sort = useMemo(() => (gridSort ? { field: gridSort.key, order: gridSort.direction } : null), [gridSort]);
	const [page, setPage] = useState(0);
	// Flips to false once a delete had to use the per-row fallback (not restorable).
	const [undoAvailable, setUndoAvailable] = useState(true);
	const [hidden, setHidden] = useState<Set<string>>(new Set());
	const [selected, setSelected] = useState<Set<string>>(new Set());
	const [drawerId, setDrawerId] = useState<string | null>(null);
	const [setValueOpen, setSetValueOpen] = useState(false);
	const [confirmDelete, setConfirmDelete] = useState(false);
	const [drafts, setDrafts] = useState<Row[]>([]);
	const [save, setSave] = useState<{ state: AutosaveState; at: number | null; retry?: () => void }>({ state: 'idle', at: null });
	const [tableTotal, setTableTotal] = useState<number | undefined>(undefined);

	const apiFilters = useMemo(() => toApiFilters(filters, columns), [filters, columns]);
	const { rows, setRows, total, hasMore, loading, error, reload } = useTableRows({ doctype, columns, search, filters: apiFilters, sort, page });
	const filtered = filters.length > 0 || search !== '';
	const visible = useMemo(() => columns.filter((c) => !hidden.has(c.key)), [columns, hidden]);
	const allRows = useMemo(() => [...rows, ...drafts], [rows, drafts]);
	const mustFill = useMemo(() => requiredWithoutDefault(schema), [schema]);

	useEffect(() => {
		const id = window.setTimeout(() => {
			setSearch(searchText.trim());
			setPage(0);
		}, 300);
		return () => window.clearTimeout(id);
	}, [searchText]);

	useEffect(() => {
		if (!filtered) return setTableTotal(total);
		let live = true;
		getTableRecords(doctype, { limit: 1 }).then((r) => live && setTableTotal(r.total), () => undefined);
		return () => {
			live = false;
		};
	}, [filtered, total, doctype]);
	useEffect(() => {
		onCount?.(tableTotal);
	}, [tableTotal, onCount]);

	const track = useCallback(async <T,>(op: () => Promise<T>): Promise<T> => {
		setSave({ state: 'saving', at: null });
		try {
			const r = await op();
			setSave({ state: 'saved', at: Date.now() });
			return r;
		} catch (err) {
			setSave({ state: 'error', at: null, retry: () => void track(op).catch(() => undefined) });
			throw err;
		}
	}, []);

	const changeCell = useCallback(
		async (rowId: string, key: string, value: CellValue): Promise<string | null> => {
			if (isDraft(rowId)) {
				const draft = drafts.find((d) => d.name === rowId);
				if (!draft) return null;
				const merged: Row = { ...draft, [key]: value };
				setDrafts((ds) => ds.map((d) => (d.name === rowId ? merged : d)));
				if (mustFill.some((k) => isBlank(merged[k]))) return null;
				const { name: _n, ...values } = merged;
				try {
					await track(() => createTableRecord(doctype, toApiValues(values)));
					setDrafts((ds) => ds.filter((d) => d.name !== rowId));
					setPage(0);
					void reload();
					return null;
				} catch (err) {
					setDrafts((ds) => ds.map((d) => (d.name === rowId ? draft : d)));
					return errorText(err, 'Could not save this row');
				}
			}
			try {
				await track(() => setOne(doctype, rowId, key, value));
				setRows((rs) => rs.map((r) => (r.name === rowId ? { ...r, [key]: value } : r)));
				return null;
			} catch (err) {
				return errorText(err, 'Could not save this value');
			}
		},
		[drafts, mustFill, doctype, track, reload, setRows],
	);

	const addRow = useCallback(async () => {
		const defaults = defaultsFor(schema);
		if (mustFill.length) {
			setDrafts((ds) => [...ds, { name: `${DRAFT_PREFIX}${++draftSeq}`, ...(defaults as Record<string, CellValue>) }]);
			return;
		}
		try {
			await track(() => createTableRecord(doctype, defaults));
			setPage(0);
			void reload();
		} catch (err) {
			toast.error('Could not add a row', { description: errorText(err) });
		}
	}, [schema, mustFill, doctype, track, reload]);

	const exportRowsCsv = useCallback(
		async (names?: string[]) => {
			const r = await serverExport(tableId, names ? { names } : { filters: apiFilters });
			if (r) return downloadCsv(r.filename || `${schema.table_name}.csv`, r.content);
			const source = names ? rows.filter((x) => names.includes(x.name)) : rows;
			downloadCsv(`${schema.table_name}.csv`, toCsv(source, visible));
			if (!names && hasMore) toast('Exported the rows on this page', { description: 'Full export needs a server update.' });
		},
		[tableId, apiFilters, schema.table_name, rows, visible, hasMore],
	);

	useImperativeHandle(ref, () => ({ addRow: () => void addRow(), exportAll: () => void exportRowsCsv() }), [addRow, exportRowsCsv]);

	const paste = async (matrix: string[][], at: { rowId: string | null; key: string }) => {
		const plan = planPaste(matrix, at, allRows, visible);
		const problems = [...plan.errors];
		try {
			await track(async () => {
				await Promise.all(plan.updates.map((u) => updateMany(doctype, [u.name], u.values)));
				if (plan.inserts.length) problems.push(...(await insertMany(doctype, plan.inserts)));
			});
		} catch (err) {
			problems.push(errorText(err));
		}
		if (problems.length) toast.error(`${problems.length} pasted ${problems.length === 1 ? 'value was' : 'values were'} skipped`, { description: problems[0] });
		await reload();
	};

	const names = [...selected].filter((n) => !isDraft(n));

	const setValue = async (key: string, value: CellValue) => {
		try {
			await track(() => updateMany(doctype, names, { [key]: value }));
			await reload();
			toast.success(`Updated ${names.length.toLocaleString()} ${names.length === 1 ? 'row' : 'rows'}`);
		} catch (err) {
			toast.error('Could not update the rows', { description: errorText(err) });
		}
	};

	const doDelete = async () => {
		const gone = names;
		try {
			const restorable = await track(() => deleteMany(doctype, gone));
			setUndoAvailable(restorable);
			setSelected(new Set());
			// Deleting every row on the last page would leave an empty page; step back.
			if (page > 0 && gone.length >= rows.length) setPage(page - 1);
			else await reload();
			toast(`Deleted ${gone.length.toLocaleString()} ${gone.length === 1 ? 'row' : 'rows'}`, {
				duration: 10000,
				action: restorable
					? {
							label: 'Undo',
							onClick: () => {
								restoreRows(doctype, gone).then(
									() => reload(),
									(err) => toast.error('Could not restore the rows', { description: errorText(err) }),
								);
							},
						}
					: undefined,
			});
		} catch (err) {
			toast.error('Could not delete the rows', { description: errorText(err) });
		}
	};

	const copySelected = () => {
		const text = toTsv(rows.filter((r) => selected.has(r.name)), visible);
		navigator.clipboard?.writeText(text).then(
			() => toast.success(`Copied ${names.length} ${names.length === 1 ? 'row' : 'rows'}`),
			() => toast.error('Could not copy'),
		);
	};

	const selectAll = async () => {
		if (total === undefined) return;
		try {
			setSelected(new Set(await fetchNames(doctype, apiFilters, search, total)));
		} catch (err) {
			toast.error('Could not select all rows', { description: errorText(err) });
		}
	};

	const from = rows.length ? page * PAGE_SIZE + 1 : 0;
	const to = page * PAGE_SIZE + rows.length;
	const hasNext = total !== undefined ? to < total : hasMore;
	const drawerIdx = drawerId ? allRows.findIndex((r) => r.name === drawerId) : -1;

	if (!loading && !error && !filtered && page === 0 && (total ?? 0) === 0 && rows.length === 0 && drafts.length === 0) {
		return (
			<DropZone
				icon={Database}
				title="No rows in this table yet"
				hint="Add rows one by one, or import many at once from a file."
				actions={
					<>
						<Button size="sm" onClick={() => void addRow()}>
							<Plus aria-hidden="true" className="mr-1.5 h-3.5 w-3.5" />
							Add row
						</Button>
						<Button size="sm" variant="outline" onClick={onImport}>
							<Upload aria-hidden="true" className="mr-1.5 h-3.5 w-3.5" />
							Import
						</Button>
					</>
				}
			/>
		);
	}

	return (
		<div>
			<GridToolbar
				search={<AskField value={searchText} onChange={setSearchText} placeholder={tableTotal !== undefined ? `Search ${tableTotal.toLocaleString()} rows` : 'Search rows'} />}
				controls={
					<>
						<FilterBuilder columns={columns} value={filters} onChange={(f) => { setFilters(f); setPage(0); }} />
						<FieldsMenu fields={columns.map((c) => ({ key: c.key, label: c.label, locked: c.tag === 'title' }))} hidden={hidden} onHiddenChange={setHidden} />
					</>
				}
				chips={
					<>
						{sort && (
							<SortChip
								field={labelOf(sort.field)}
								direction={sort.order}
								directionLabel={sortDirectionLabel(columns.find((c) => c.key === sort.field)?.type ?? 'text', sort.order)}
								onToggle={() => setGridSort({ key: sort.field, direction: sort.order === 'asc' ? 'desc' : 'asc' })}
								onRemove={() => { setGridSort(null); setPage(0); }}
							/>
						)}
					</>
				}
				end={
					<>
						{total !== undefined && tableTotal !== undefined && <MatchCount shown={total} total={tableTotal} />}
						<AutosaveStatus state={save.state} savedAt={save.at} onRetry={save.retry} />
					</>
				}
			/>
			{error && (
				<div role="alert" className="mb-3 flex items-center gap-3 text-ui-text text-steel">
					<span>{error}</span>
					<Button size="sm" variant="outline" onClick={() => void reload()}>Try again</Button>
				</div>
			)}
			{drafts.length > 0 && mustFill.length > 0 && (
				<p className="mb-2 text-micro text-steel">Fill {mustFill.map(labelOf).join(', ')} to save the new row.</p>
			)}
			<div aria-busy={loading}>
				<DataGrid<Row>
					label={schema.table_name}
					columns={visible}
					rows={allRows}
					getRowId={(r) => r.name}
					onCellChange={changeCell}
					selected={selected}
					onSelectedChange={setSelected}
					onAddRow={() => void addRow()}
					onOpenRow={setDrawerId}
					onPaste={(m, at) => void paste(m, at)}
					rowNumberOffset={page * PAGE_SIZE}
					sort={gridSort}
					onSortChange={(next) => { setGridSort(next); setPage(0); }}
					empty={<p className="py-8 text-center text-ui-text text-steel">No rows match. Clear a filter or the search to see more.</p>}
				/>
			</div>
			<GridFooter from={from} to={to} total={total ?? (hasMore ? to : null)} approximate={total === undefined && hasMore} pager={<Pager page={page} hasNext={hasNext} onPage={setPage} />} />
			<BulkActionBar
				count={selected.size}
				onClear={() => setSelected(new Set())}
				selectAll={total !== undefined ? { total, onClick: () => void selectAll() } : undefined}
				actions={[
					{ label: 'Set value', onClick: () => setSetValueOpen(true) },
					{ label: 'Copy', onClick: copySelected },
					{ label: 'Export', onClick: () => void exportRowsCsv(names) },
					{ label: 'Delete', destructive: true, onClick: () => setConfirmDelete(true) },
				]}
			/>
			<SetValueDialog open={setValueOpen} onOpenChange={setSetValueOpen} columns={columns} count={names.length} onApply={setValue} />
			<ConfirmDestructive
				open={confirmDelete}
				onOpenChange={setConfirmDelete}
				title={`Delete ${names.length.toLocaleString()} ${names.length === 1 ? 'row' : 'rows'}?`}
				consequence="These rows will be removed from the table."
				recovery={undoAvailable ? 'You can undo this right after.' : 'This cannot be undone.'}
				actionLabel="Delete"
				onConfirm={doDelete}
			/>
			{drawerIdx >= 0 && (
				<RecordPanel
					row={allRows[drawerIdx]}
					columns={columns}
					position={total !== undefined ? { index: page * PAGE_SIZE + drawerIdx + 1, total } : undefined}
					onClose={() => setDrawerId(null)}
					onPrev={drawerIdx > 0 ? () => setDrawerId(allRows[drawerIdx - 1].name) : undefined}
					onNext={drawerIdx < allRows.length - 1 ? () => setDrawerId(allRows[drawerIdx + 1].name) : undefined}
					onChange={changeCell}
				/>
			)}
		</div>
	);
});

function Pager({ page, hasNext, onPage }: { page: number; hasNext: boolean; onPage: (p: number) => void }) {
	return (
		<span className="inline-flex items-center gap-1">
			<Button size="sm" variant="outline" disabled={page === 0} onClick={() => onPage(page - 1)}>Previous</Button>
			<Button size="sm" variant="outline" disabled={!hasNext} onClick={() => onPage(page + 1)}>Next</Button>
		</span>
	);
}
