import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { FormField, FormItem, FormLabel, FormControl, FormDescription } from '@/components/ui/form';
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
	isEditing?: boolean;
	key?: string | number;
}

export function FieldInput({ field, value, onChange, isEditing = true }: FieldInputProps) {
	const isRequired = field.reqd === 1;
	const isReadOnly = field.read_only === 1;

	if (!isEditing) {
		return <FieldView field={field} value={value} />;
	}

	return (
		<FormField
			name={field.fieldname}
			render={() => (
				<FormItem>
					<FormLabel>
						{field.label}
						{isRequired && <span className="text-destructive ml-1">*</span>}
					</FormLabel>

					<FormControl>
						{(field.fieldtype === 'Data' || field.fieldtype === 'Phone') ? (
							<Input
								type={field.fieldtype === 'Phone' ? 'tel' : 'text'}
								value={(value as string) || ''}
								onChange={(event) => onChange(event.target.value)}
								disabled={isReadOnly}
								placeholder={field.description || ''}
								className="h-8 text-sm rounded-none border-line"
							/>
						) : (field.fieldtype === 'Text' ||
							field.fieldtype === 'Small Text' ||
							field.fieldtype === 'Long Text') ? (
							<Textarea
								value={(value as string) || ''}
								onChange={(event) => onChange(event.target.value)}
								disabled={isReadOnly}
								placeholder={field.description || ''}
								rows={field.fieldtype === 'Long Text' ? 6 : 3}
								className="text-sm rounded-none border-line"
							/>
						) : (field.fieldtype === 'Int' ||
							field.fieldtype === 'Float' ||
							field.fieldtype === 'Currency' ||
							field.fieldtype === 'Percent') ? (
							<Input
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
								className="h-8 text-sm rounded-none border-line"
							/>
						) : field.fieldtype === 'Check' ? (
							<div className="flex items-center gap-2 pt-1">
								<Checkbox
									checked={value === 1 || value === true}
									onCheckedChange={(checked) => onChange(checked ? 1 : 0)}
									disabled={isReadOnly}
									className="rounded-none border-line"
								/>
								{field.description && (
									<span className="text-xs text-steel-soft">{field.description}</span>
								)}
							</div>
						) : (field.fieldtype === 'Date' || field.fieldtype === 'Datetime') ? (
							<Input
								type={field.fieldtype === 'Datetime' ? 'datetime-local' : 'date'}
								value={(value as string) || ''}
								onChange={(event) => onChange(event.target.value)}
								disabled={isReadOnly}
								className="h-8 text-sm rounded-none border-line"
							/>
						) : field.fieldtype === 'Time' ? (
							<Input
								type="time"
								value={(value as string) || ''}
								onChange={(event) => onChange(event.target.value)}
								disabled={isReadOnly}
								className="h-8 text-sm rounded-none border-line"
							/>
						) : field.fieldtype === 'Duration' ? (
							<Input
								type="text"
								value={(value as string) || ''}
								onChange={(event) => onChange(event.target.value)}
								disabled={isReadOnly}
								placeholder="e.g. 1h 30m"
								className="h-8 text-sm rounded-none border-line"
							/>
						) : field.fieldtype === 'Select' ? (
							<Select
								value={(value as string) || ''}
								onValueChange={onChange}
								disabled={isReadOnly}
							>
								<SelectTrigger className="h-8 text-sm rounded-none border-line">
									<SelectValue placeholder="Select..." />
								</SelectTrigger>
								<SelectContent className="rounded-none border-line">
									{(field.options || '')
										.split('\n')
										.filter(Boolean)
										.map((option) => (
											<SelectItem key={option} value={option} className="rounded-none">
												{option}
											</SelectItem>
										))}
								</SelectContent>
							</Select>
						) : field.fieldtype === 'Link' ? (
							<Input
								type="text"
								value={(value as string) || ''}
								onChange={(event) => onChange(event.target.value)}
								disabled={isReadOnly}
								placeholder={`Link to ${field.options || 'table'}...`}
								className="h-8 text-sm rounded-none border-line"
							/>
						) : field.fieldtype === 'Rating' ? (
							<Input
								type="number"
								min={0}
								max={1}
								step={0.2}
								value={value !== undefined && value !== null && value !== '' ? String(value) : ''}
								onChange={(event) => onChange(parseFloat(event.target.value) || 0)}
								disabled={isReadOnly}
								className="h-8 text-sm rounded-none border-line"
							/>
						) : field.fieldtype === 'Color' ? (
							<Input
								type="color"
								value={(value as string) || undefined}
								onChange={(event) => onChange(event.target.value)}
								disabled={isReadOnly}
								className="h-8 w-16 rounded-none border-line p-1"
							/>
						) : null}
					</FormControl>
					{field.description && field.fieldtype !== 'Check' && (
						<FormDescription>{field.description}</FormDescription>
					)}
				</FormItem>
			)}
		/>
	);
}

export function FieldView({ field, value }: { field: DataTableFieldDef, value: unknown }) {
    let displayValue: React.ReactNode = String(value ?? '');
    
    if (field.fieldtype === 'Check') {
        const isChecked = value === 1 || value === true;
        displayValue = isChecked ? (
            <span className="inline-flex items-center px-2 py-0.5 rounded-none border border-line bg-paper-deep text-xs font-medium text-ink">Yes</span>
        ) : (
            <span className="inline-flex items-center px-2 py-0.5 rounded-none border border-line bg-panel text-xs font-medium text-steel">No</span>
        );
    } else if (field.fieldtype === 'Select' || field.fieldtype === 'Link') {
        if (value) {
            displayValue = (
                <span className="inline-flex items-center px-2 py-0.5 rounded-none border border-line bg-paper-deep text-sm font-medium text-ink">
                    {String(value)}
                </span>
            );
        } else {
            displayValue = <span className="text-steel-soft italic text-sm">Empty</span>;
        }
    } else if (field.fieldtype === 'Text' || field.fieldtype === 'Small Text' || field.fieldtype === 'Long Text') {
        displayValue = value ? (
            <div className="whitespace-pre-wrap text-sm text-ink bg-paper-deep p-3 border border-line rounded-none">
                {String(value)}
            </div>
        ) : (
            <span className="text-steel-soft italic text-sm">Empty</span>
        );
    } else if (field.fieldtype === 'Date' || field.fieldtype === 'Datetime') {
        if (value) {
            const d = new Date(String(value));
            displayValue = !isNaN(d.getTime()) ? (
                <span className="text-sm text-ink font-medium">{d.toLocaleDateString()} {field.fieldtype === 'Datetime' ? d.toLocaleTimeString() : ''}</span>
            ) : <span className="text-sm text-ink font-medium">{String(value)}</span>;
        } else {
            displayValue = <span className="text-steel-soft italic text-sm">Empty</span>;
        }
    } else {
        displayValue = (value !== undefined && value !== null && value !== '') ? (
            <span className="text-sm text-ink font-medium">{String(value)}</span>
        ) : (
            <span className="text-steel-soft italic text-sm">Empty</span>
        );
    }

    return (
        <FormItem className="space-y-1.5 py-1">
            <FormLabel className="text-sm text-steel">
                {field.label}
            </FormLabel>
            <div>
                {displayValue}
            </div>
            {field.description && field.fieldtype !== 'Check' && (
				<FormDescription className="text-[10px] text-steel-soft">{field.description}</FormDescription>
			)}
        </FormItem>
    );
}
