import { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Field } from '@/components/ui/field';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Spinner } from '@/components/ui/spinner';
import { ImportMapper, ChangeImpactNotice, SKIP_COLUMN, type SourceColumn, type TargetField } from '@/components/grid';
import { DropZone, ProgressRow } from '@/components/patterns';
import { toColumnType } from '@/data/fieldTypeLabels';
import type { DataTableSchema, ImportMode } from '@/types/dataTable.types';
import { useImportFlow } from './useImportFlow';

export interface ImportDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	schema: DataTableSchema;
	onImported?: () => void;
}

const MODES: { value: ImportMode; label: string; hint: string }[] = [
	{ value: 'insert', label: 'Add rows', hint: 'Keep existing rows and add these.' },
	{ value: 'update', label: 'Update by key', hint: 'Match rows on a key field and update them.' },
	{ value: 'replace', label: 'Replace all rows', hint: 'Delete every existing row first.' },
];

export function downloadRejected(csv: string, filename = 'rejected-rows.csv') {
	const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
	const a = document.createElement('a');
	a.href = url;
	a.download = filename;
	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);
	URL.revokeObjectURL(url);
}

export function ImportDialog({ open, onOpenChange, schema, onImported }: ImportDialogProps) {
	const flow = useImportFlow(schema.name, onImported);
	const [sheetUrl, setSheetUrl] = useState('');
	const { reset } = flow;

	useEffect(() => {
		if (!open) {
			reset();
			setSheetUrl('');
		}
	}, [open, reset]);

	const targets: TargetField[] = useMemo(
		() => schema.fields.map((f) => ({ key: f.fieldname, label: f.label, type: toColumnType(f.fieldtype) })),
		[schema.fields]
	);

	const { preview, phase } = flow;
	const columns: SourceColumn[] = useMemo(
		() =>
			(preview?.columns ?? []).map((c, i) => ({
				header: c.header,
				samples: (preview?.sample_rows ?? []).slice(0, 3).map((r) => String(r[i] ?? '')),
				detected: toColumnType(c.detected_type),
				target: flow.mapping[c.header] ?? null,
				problems: c.issues > 0 ? { count: c.issues, reason: 'will not fit this field' } : undefined,
			})),
		[preview, flow.mapping]
	);

	const validRows = preview?.valid_rows ?? 0;
	const keyMissing = flow.mode === 'update' && !flow.keyField;
	const replaceBlocked = flow.mode === 'replace' && !flow.confirmReplace;
	const canRun = phase === 'reviewing' && validRows > 0 && !keyMissing && !replaceBlocked;

	const modePicker = (
		<div className="space-y-3">
			<RadioGroup value={flow.mode} onValueChange={(v) => flow.setMode(v as ImportMode)} aria-label="Import mode">
				{MODES.map((m) => (
					<div key={m.value} className="flex items-start gap-2">
						<RadioGroupItem id={`mode-${m.value}`} value={m.value} />
						<Label htmlFor={`mode-${m.value}`} className="flex flex-col">
							<span>{m.label}</span>
							<span className="text-steel">{m.hint}</span>
						</Label>
					</div>
				))}
			</RadioGroup>
			{flow.mode === 'update' && (
				<Field label="Key field" hint="Rows with the same value here are updated.">
					{(p) => (
						<Select value={flow.keyField} onValueChange={flow.setKeyField}>
							<SelectTrigger id={p.id} aria-label="Key field">
								<SelectValue placeholder="Choose a field" />
							</SelectTrigger>
							<SelectContent>
								{targets.map((t) => (
									<SelectItem key={t.key} value={t.key}>
										{t.label}
									</SelectItem>
								))}
							</SelectContent>
						</Select>
					)}
				</Field>
			)}
			{flow.mode === 'replace' && (
				<>
					<ChangeImpactNotice
						title="Replace all rows"
						severity="error"
						lines={[
							{ count: validRows, label: 'rows from the file become the whole table', kind: 'safe' },
							{ count: 1, label: 'existing rows are deleted first', kind: 'loss' },
						]}
					/>
					<div className="flex items-center gap-2">
						<Checkbox id="confirm-replace" checked={flow.confirmReplace} onCheckedChange={(v) => flow.setConfirmReplace(v === true)} />
						<Label htmlFor="confirm-replace">Delete all existing rows and import</Label>
					</div>
				</>
			)}
		</div>
	);

	const r = flow.result;
	return (
		<Dialog open={open} onOpenChange={(o) => !(phase === 'running') && onOpenChange(o)}>
			<DialogContent className="sm:max-w-3xl">
				<DialogHeader>
					<DialogTitle>Import into {schema.table_name}</DialogTitle>
					<DialogDescription>Upload a CSV or Excel file, check the columns, then import the valid rows.</DialogDescription>
				</DialogHeader>

				{phase === 'pick' && (
					<div className="space-y-4">
						<DropZone
							title="Choose a file or drop it here"
							hint="CSV or Excel (.xlsx). The first row is the header."
							accept=".csv,.xlsx"
							onFiles={(files) => files[0] && flow.chooseFile(files[0])}
						/>
						<div className="flex items-end gap-2">
							<Field label="Or a Google Sheet link" className="flex-1">
								{(p) => <Input id={p.id} value={sheetUrl} onChange={(e) => setSheetUrl(e.target.value)} placeholder="https://docs.google.com/spreadsheets/…" />}
							</Field>
							<Button variant="outline" disabled={!sheetUrl.trim()} onClick={() => flow.startSheet(sheetUrl.trim())}>
								Import sheet
							</Button>
						</div>
					</div>
				)}
				{phase === 'uploading' && (
					<p className="flex items-center gap-2 py-8 text-ui-text text-steel">
						<Spinner /> Reading your file…
					</p>
				)}
				{phase === 'unsupported' && (
					<p role="alert" className="py-6 text-ui-text">
						Import preview needs a newer server. Update Huf and try again.
					</p>
				)}
				{phase === 'error' && (
					<p role="alert" className="py-6 text-ui-text text-destructive">
						{flow.error || 'Import failed.'}
					</p>
				)}
				{phase === 'reviewing' && preview && (
					<ImportMapper
						header={modePicker}
						columns={columns}
						targets={targets}
						onMap={(h, t) => flow.map(h, t === SKIP_COLUMN ? null : t)}
						preview={{ headers: preview.columns.map((c) => c.header), rows: preview.sample_rows.slice(0, 5).map((row) => row.map((v) => String(v ?? ''))) }}
						rejected={preview.invalid_rows.map((x) => ({ row: x.row, reason: x.message }))}
						totals={{ valid: validRows, rejected: preview.invalid_rows.length }}
					/>
				)}
				{phase === 'running' && <ProgressRow label="Importing" source={schema.table_name} done={flow.progress} total={flow.progress ? 100 : undefined} />}
				{phase === 'done' && r && (
					<div className="space-y-2 py-4 text-ui-text" data-testid="import-summary">
						<p>
							{r.inserted} added, {r.updated} updated, {r.rejected} rejected.
						</p>
						{r.rejected > 0 && r.rejected_csv && (
							<Button variant="outline" size="sm" onClick={() => downloadRejected(r.rejected_csv)}>
								Download rejected rows
							</Button>
						)}
					</div>
				)}

				<DialogFooter>
					{phase === 'done' || phase === 'unsupported' ? (
						<Button onClick={() => onOpenChange(false)}>Close</Button>
					) : phase === 'error' ? (
						<Button variant="outline" onClick={reset}>
							Try again
						</Button>
					) : (
						<>
							<Button variant="outline" disabled={phase === 'running'} onClick={() => onOpenChange(false)}>
								Cancel
							</Button>
							{phase === 'reviewing' && (
								<Button disabled={!canRun} onClick={flow.submit}>
									Import {validRows.toLocaleString()} valid rows
								</Button>
							)}
						</>
					)}
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
