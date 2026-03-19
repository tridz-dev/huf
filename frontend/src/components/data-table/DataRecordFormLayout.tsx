import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@/components/ui/select';
import type { DataTableFieldDef } from '@/types/dataTable.types';

export interface LayoutSection {
	label?: string;
	columns: DataTableFieldDef[][];
}

const LAYOUT_DEFAULT_LABELS = new Set(['section break', 'column break']);

export function buildFormLayout(fields: DataTableFieldDef[]): LayoutSection[] {
	const sections: LayoutSection[] = [{ columns: [[]] }];
	for (const field of fields) {
		if (field.fieldtype === 'Section Break') {
			const raw = field.label?.trim();
			const label = raw && !LAYOUT_DEFAULT_LABELS.has(raw.toLowerCase()) ? raw : undefined;
			sections.push({ label, columns: [[]] });
		} else if (field.fieldtype === 'Column Break') {
			sections[sections.length - 1].columns.push([]);
		} else {
			const currentSection = sections[sections.length - 1];
			currentSection.columns[currentSection.columns.length - 1].push(field);
		}
	}
	return sections.filter((section) => section.columns.some((col) => col.length > 0));
}

export function initFormData(
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

export interface FieldInputProps {
	field: DataTableFieldDef;
	value: unknown;
	onChange: (value: unknown) => void;
}

export function FieldInput({ field, value, onChange }: FieldInputProps) {
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
					onChange={(event) => onChange(event.target.value)}
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
					onChange={(event) => onChange(event.target.value)}
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
					onChange={(event) => {
						const raw = event.target.value;
						if (raw === '') {
							onChange('');
						} else if (field.fieldtype === 'Int') {
							onChange(parseInt(raw, 10) || 0);
						} else {
							onChange(parseFloat(raw) || 0);
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
					onChange={(event) => onChange(event.target.value)}
					disabled={isReadOnly}
					className="h-8 text-sm"
				/>
			)}

			{field.fieldtype === 'Time' && (
				<Input
					id={`field-${field.fieldname}`}
					type="time"
					value={(value as string) || ''}
					onChange={(event) => onChange(event.target.value)}
					disabled={isReadOnly}
					className="h-8 text-sm"
				/>
			)}

			{field.fieldtype === 'Duration' && (
				<Input
					id={`field-${field.fieldname}`}
					type="text"
					value={(value as string) || ''}
					onChange={(event) => onChange(event.target.value)}
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
							.map((option) => (
								<SelectItem key={option} value={option}>
									{option}
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
					onChange={(event) => onChange(event.target.value)}
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
					onChange={(event) => onChange(parseFloat(event.target.value) || 0)}
					disabled={isReadOnly}
					className="h-8 text-sm"
				/>
			)}

			{field.fieldtype === 'Color' && (
				<Input
					id={`field-${field.fieldname}`}
					type="color"
					value={(value as string) || '#000000'}
					onChange={(event) => onChange(event.target.value)}
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

