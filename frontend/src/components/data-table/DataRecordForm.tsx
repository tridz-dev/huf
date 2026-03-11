import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@/components/ui/select';
import {
	Sheet,
	SheetContent,
	SheetHeader,
	SheetTitle,
	SheetFooter,
} from '@/components/ui/sheet';
import { Separator } from '@/components/ui/separator';
import { createTableRecord, updateTableRecord } from '@/services/dataTableApi';
import type { DataTableFieldDef } from '@/types/dataTable.types';

interface DataRecordFormProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	doctypeName: string;
	fields: DataTableFieldDef[];
	record?: Record<string, unknown> | null;
	onSaved: () => void;
}

export function DataRecordForm({
	open,
	onOpenChange,
	doctypeName,
	fields,
	record,
	onSaved,
}: DataRecordFormProps) {
	const isEdit = !!record;
	const [formData, setFormData] = useState<Record<string, unknown>>(() =>
		initFormData(fields, record)
	);
	const [saving, setSaving] = useState(false);

	useEffect(() => {
		if (open) {
			setFormData(initFormData(fields, record));
		}
	}, [open, record, fields]);

	const handleOpen = (isOpen: boolean) => {
		onOpenChange(isOpen);
	};

	const setValue = (fieldname: string, value: unknown) => {
		setFormData((prev) => ({ ...prev, [fieldname]: value }));
	};

	const handleSave = async () => {
		setSaving(true);
		try {
			if (isEdit && record?.name) {
				await updateTableRecord(doctypeName, record.name as string, formData);
				toast.success('Record updated');
			} else {
				await createTableRecord(doctypeName, formData);
				toast.success('Record created');
			}
			onSaved();
			onOpenChange(false);
		} catch (err: any) {
			toast.error(isEdit ? 'Failed to update record' : 'Failed to create record', {
				description: err.message,
			});
		} finally {
			setSaving(false);
		}
	};

	const dataFields = fields.filter(
		(f) => f.fieldtype !== 'Section Break' && f.fieldtype !== 'Column Break'
	);

	return (
		<Sheet open={open} onOpenChange={handleOpen}>
			<SheetContent className="overflow-y-auto sm:max-w-lg">
				<SheetHeader>
					<SheetTitle>{isEdit ? 'Edit Record' : 'Add New Record'}</SheetTitle>
				</SheetHeader>
				<div className="space-y-4 py-4">
					{fields.map((field, idx) => {
						if (field.fieldtype === 'Section Break') {
							return (
								<div key={`${field.fieldname}-${idx}`}>
									{idx > 0 && <Separator className="my-4" />}
									{field.label && (
										<p className="text-sm font-medium text-muted-foreground">
											{field.label}
										</p>
									)}
								</div>
							);
						}
						if (field.fieldtype === 'Column Break') {
							return null;
						}
						return (
							<FieldInput
								key={field.fieldname}
								field={field}
								value={formData[field.fieldname]}
								onChange={(val) => setValue(field.fieldname, val)}
							/>
						);
					})}

					{dataFields.length === 0 && (
						<p className="text-sm text-muted-foreground text-center py-8">
							No fields defined
						</p>
					)}
				</div>
				<SheetFooter className="gap-2 pt-4">
					<Button variant="outline" onClick={() => onOpenChange(false)}>
						Cancel
					</Button>
					<Button onClick={handleSave} disabled={saving}>
						{saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
						{isEdit ? 'Save Changes' : 'Create Record'}
					</Button>
				</SheetFooter>
			</SheetContent>
		</Sheet>
	);
}

function initFormData(
	fields: DataTableFieldDef[],
	record?: Record<string, unknown> | null
): Record<string, unknown> {
	const data: Record<string, unknown> = {};
	for (const field of fields) {
		if (field.fieldtype === 'Section Break' || field.fieldtype === 'Column Break') continue;
		if (record) {
			data[field.fieldname] = record[field.fieldname] ?? field.default ?? '';
		} else {
			data[field.fieldname] = field.default ?? (field.fieldtype === 'Check' ? 0 : '');
		}
	}
	return data;
}

interface FieldInputProps {
	field: DataTableFieldDef;
	value: unknown;
	onChange: (value: unknown) => void;
}

function FieldInput({ field, value, onChange }: FieldInputProps) {
	const isRequired = field.reqd === 1;
	const isReadOnly = field.read_only === 1;

	return (
		<div className="space-y-1.5">
			<Label htmlFor={`field-${field.fieldname}`} className="text-sm">
				{field.label}
				{isRequired && <span className="text-destructive ml-1">*</span>}
			</Label>

			{(field.fieldtype === 'Data' || field.fieldtype === 'Phone') && (
				<Input
					id={`field-${field.fieldname}`}
					type={field.fieldtype === 'Phone' ? 'tel' : 'text'}
					value={(value as string) || ''}
					onChange={(e) => onChange(e.target.value)}
					disabled={isReadOnly}
					placeholder={field.description || ''}
					className="h-8 text-sm"
				/>
			)}

			{(field.fieldtype === 'Text' ||
				field.fieldtype === 'Small Text' ||
				field.fieldtype === 'Long Text') && (
					<Textarea
						id={`field-${field.fieldname}`}
						value={(value as string) || ''}
						onChange={(e) => onChange(e.target.value)}
						disabled={isReadOnly}
						placeholder={field.description || ''}
						rows={field.fieldtype === 'Long Text' ? 6 : 3}
						className="text-sm"
					/>
				)}

			{(field.fieldtype === 'Int' ||
				field.fieldtype === 'Float' ||
				field.fieldtype === 'Currency' ||
				field.fieldtype === 'Percent') && (
					<Input
						id={`field-${field.fieldname}`}
						type="number"
						value={value !== undefined && value !== null && value !== '' ? String(value) : ''}
						onChange={(e) => {
							const v = e.target.value;
							if (v === '') {
								onChange('');
							} else if (field.fieldtype === 'Int') {
								onChange(parseInt(v, 10) || 0);
							} else {
								onChange(parseFloat(v) || 0);
							}
						}}
						disabled={isReadOnly}
						min={field.non_negative === 1 ? 0 : undefined}
						step={field.fieldtype === 'Int' ? 1 : 'any'}
						className="h-8 text-sm"
					/>
				)}

			{field.fieldtype === 'Check' && (
				<div className="flex items-center gap-2 pt-1">
					<Checkbox
						id={`field-${field.fieldname}`}
						checked={value === 1 || value === true}
						onCheckedChange={(checked) => onChange(checked ? 1 : 0)}
						disabled={isReadOnly}
					/>
					{field.description && (
						<span className="text-xs text-muted-foreground">{field.description}</span>
					)}
				</div>
			)}

			{(field.fieldtype === 'Date' || field.fieldtype === 'Datetime') && (
				<Input
					id={`field-${field.fieldname}`}
					type={field.fieldtype === 'Datetime' ? 'datetime-local' : 'date'}
					value={(value as string) || ''}
					onChange={(e) => onChange(e.target.value)}
					disabled={isReadOnly}
					className="h-8 text-sm"
				/>
			)}

			{field.fieldtype === 'Time' && (
				<Input
					id={`field-${field.fieldname}`}
					type="time"
					value={(value as string) || ''}
					onChange={(e) => onChange(e.target.value)}
					disabled={isReadOnly}
					className="h-8 text-sm"
				/>
			)}

			{field.fieldtype === 'Duration' && (
				<Input
					id={`field-${field.fieldname}`}
					type="text"
					value={(value as string) || ''}
					onChange={(e) => onChange(e.target.value)}
					disabled={isReadOnly}
					placeholder="e.g. 1h 30m"
					className="h-8 text-sm"
				/>
			)}

			{field.fieldtype === 'Select' && (
				<Select
					value={(value as string) || ''}
					onValueChange={onChange}
					disabled={isReadOnly}
				>
					<SelectTrigger className="h-8 text-sm">
						<SelectValue placeholder="Select..." />
					</SelectTrigger>
					<SelectContent>
						{(field.options || '')
							.split('\n')
							.filter(Boolean)
							.map((opt) => (
								<SelectItem key={opt} value={opt}>
									{opt}
								</SelectItem>
							))}
					</SelectContent>
				</Select>
			)}

			{field.fieldtype === 'Link' && (
				<Input
					id={`field-${field.fieldname}`}
					type="text"
					value={(value as string) || ''}
					onChange={(e) => onChange(e.target.value)}
					disabled={isReadOnly}
					placeholder={`Link to ${field.options || 'table'}...`}
					className="h-8 text-sm"
				/>
			)}

			{field.fieldtype === 'Rating' && (
				<Input
					id={`field-${field.fieldname}`}
					type="number"
					min={0}
					max={1}
					step={0.2}
					value={value !== undefined && value !== null && value !== '' ? String(value) : ''}
					onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
					disabled={isReadOnly}
					className="h-8 text-sm"
				/>
			)}

			{field.fieldtype === 'Color' && (
				<Input
					id={`field-${field.fieldname}`}
					type="color"
					value={(value as string) || '#000000'}
					onChange={(e) => onChange(e.target.value)}
					disabled={isReadOnly}
					className="h-8 w-16"
				/>
			)}

			{field.description && field.fieldtype !== 'Check' && (
				<p className="text-[10px] text-muted-foreground">{field.description}</p>
			)}
		</div>
	);
}
