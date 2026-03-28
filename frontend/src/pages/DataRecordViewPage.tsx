import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Loader2, Trash2, ArrowLeft } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
	getTableRecord,
	updateTableRecord,
	deleteTableRecord,
	createTableRecord,
} from '@/services/dataTableApi';
import type { DataTableSchema, DataTableFieldDef } from '@/types/dataTable.types';
import { buildFormLayout, FieldInput, initFormData } from '@/components/data-table/DataRecordFormLayout';

export interface DataRecordViewPageProps {
	schema: DataTableSchema | null;
	onHeaderActionsChange?: (actions: ReactNode | null) => void;
}

export function DataRecordViewPage({ schema, onHeaderActionsChange }: DataRecordViewPageProps) {
	const { recordName, tableId } = useParams<{ recordName: string; tableId: string }>();
	const navigate = useNavigate();
	const isNew = recordName === 'new';

	const [record, setRecord] = useState<Record<string, unknown> | null>(null);
	const [formData, setFormData] = useState<Record<string, unknown>>({});
	const [loading, setLoading] = useState(true);
	const [saving, setSaving] = useState(false);
	const [deleting, setDeleting] = useState(false);

	const hasSchema = !!schema;

	const loadRecord = useCallback(async () => {
		if (!schema || !recordName || isNew) return;
		setLoading(true);
		try {
			const result = await getTableRecord(schema.doctype_name, recordName);
			setRecord(result);
			setFormData(initFormData(schema.fields, result));
		} catch (error: any) {
			toast.error('Failed to load record', { description: error?.message });
			navigate(tableId ? `/data/${tableId}` : '/data');
		} finally {
			setLoading(false);
		}
	}, [schema, recordName, isNew, navigate, tableId]);

	useEffect(() => {
		if (schema && recordName && !isNew) {
			loadRecord();
		}
	}, [schema, recordName, isNew, loadRecord]);

	useEffect(() => {
		if (schema && isNew) {
			setFormData(initFormData(schema.fields, null));
			setLoading(false);
		}
	}, [schema, isNew]);

	const isDirty = useMemo(() => {
		if (isNew) return true;
		if (!record) return false;
		return Object.keys(formData).some((key) => formData[key] !== record[key]);
	}, [formData, record, isNew]);

	const handleChange = (fieldname: string, value: unknown) => {
		setFormData((prev) => ({ ...prev, [fieldname]: value }));
	};

	const handleSave = useCallback(async () => {
		if (!schema) return;
		setSaving(true);
		try {
			if (isNew) {
				const created = await createTableRecord(schema.doctype_name, formData);
				toast.success('Record created');
				if (created?.name && tableId) {
					navigate(`/data/${tableId}/${created.name as string}`);
				} else if (tableId) {
					navigate(`/data/${tableId}`);
				}
			} else if (recordName) {
				await updateTableRecord(schema.doctype_name, recordName, formData);
				toast.success('Record updated');
			}
		} catch (error: any) {
			toast.error('Failed to save record', { description: error?.message });
		} finally {
			setSaving(false);
		}
	}, [schema, isNew, formData, tableId, navigate, recordName]);

	const handleDelete = useCallback(async () => {
		if (!schema || !recordName || isNew) return;
		setDeleting(true);
		try {
			await deleteTableRecord(schema.doctype_name, recordName);
			toast.success('Record deleted');
			navigate(tableId ? `/data/${tableId}` : '/data');
		} catch (error: any) {
			toast.error('Failed to delete record', { description: error?.message });
		} finally {
			setDeleting(false);
		}
	}, [schema, recordName, isNew, navigate, tableId]);

	useEffect(() => {
		if (!onHeaderActionsChange) return;
		onHeaderActionsChange(
			<div className="flex items-center gap-2">
				<Button
					variant="outline"
					size="sm"
					onClick={() => navigate(tableId ? `/data/${tableId}` : '/data')}
				>
					<ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
					Back
				</Button>
				{!isNew && (
					<Button
						variant="outline"
						size="sm"
						onClick={handleDelete}
						disabled={deleting}
						className="text-destructive border-destructive/40"
					>
						{deleting && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
						<Trash2 className="w-3.5 h-3.5 mr-1.5" />
						Delete
					</Button>
				)}
				<Button
					size="sm"
					onClick={handleSave}
					disabled={( !isDirty && !isNew ) || saving || !hasSchema}
				>
					{saving && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
					Save
				</Button>
			</div>
		);

		return () => onHeaderActionsChange(null);
	}, [onHeaderActionsChange, handleDelete, handleSave, deleting, saving, isDirty, hasSchema, navigate, tableId, isNew]);

	if (!schema || loading) {
		return (
			<div className="flex items-center justify-center h-full">
				<Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
			</div>
		);
	}

	const dataFields: DataTableFieldDef[] = schema.fields.filter(
		(field) => field.fieldtype !== 'Section Break' && field.fieldtype !== 'Column Break'
	);
	const sections = buildFormLayout(schema.fields);

	const titleField = schema.title_field_name;
	const recordTitle = isNew
		? 'New Record'
		: (record && titleField && (record[titleField] as string)) || (recordName as string);

	return (
		<div className="h-full overflow-auto">
			<div className="p-6 space-y-6 max-w-5xl mx-auto">
				<div className="space-y-1">
					<h2 className="text-xl font-semibold">{recordTitle}</h2>
					<p className="text-sm text-muted-foreground">{schema.table_name}</p>
				</div>

				<Separator />

				<div className="space-y-4">
					{sections.map((section, index) => (
						<div key={index}>
							{index > 0 && <Separator className="my-4" />}
							{section.label && (
								<p className="text-sm font-medium text-muted-foreground mb-3">
									{section.label}
								</p>
							)}
							{section.columns.length > 1 ? (
								<div
									className="grid gap-4"
									style={{
										gridTemplateColumns: `repeat(${section.columns.length}, minmax(0, 1fr))`,
									}}
								>
									{section.columns.map((column, columnIndex) => (
										<div key={columnIndex} className="space-y-4">
											{column.map((field) => (
												<FieldInput
													key={field.fieldname}
													field={field}
													value={formData[field.fieldname]}
													onChange={(value) => handleChange(field.fieldname, value)}
												/>
											))}
										</div>
									))}
								</div>
							) : (
								<div className="space-y-4">
									{section.columns[0]?.map((field) => (
										<FieldInput
											key={field.fieldname}
											field={field}
											value={formData[field.fieldname]}
											onChange={(value) => handleChange(field.fieldname, value)}
										/>
									))}
								</div>
							)}
						</div>
					))}

					{dataFields.length === 0 && (
						<p className="text-sm text-muted-foreground text-center py-8">
							No fields defined
						</p>
					)}
				</div>
			</div>
		</div>
	);
}

