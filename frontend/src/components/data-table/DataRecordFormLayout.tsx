import { useState, useRef } from 'react';
import { Loader2, Upload, X, Paperclip } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
	
	const [isUploading, setIsUploading] = useState(false);
	const fileInputRef = useRef<HTMLInputElement>(null);

	const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
		const file = event.target.files?.[0];
		if (!file) return;

		setIsUploading(true);
		try {
			const formData = new FormData();
			formData.append('file', file, file.name);
			formData.append('is_private', '1');
			formData.append('fieldname', field.fieldname);

			const response = await fetch('/api/method/upload_file', {
				method: 'POST',
				body: formData,
				headers: {
					'Accept': 'application/json',
				},
			});

			if (!response.ok) throw new Error('Upload failed');
			const data = await response.json();
			if (data.message && data.message.file_url) {
				onChange(data.message.file_url);
			}
		} catch (err) {
			console.error(err);
		} finally {
			setIsUploading(false);
			if (fileInputRef.current) {
				fileInputRef.current.value = '';
			}
		}
	};

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

			{(field.fieldtype === 'Attach' || field.fieldtype === 'Attach Image') && (
				<div className="space-y-2">
					<input
						type="file"
						className="hidden"
						ref={fileInputRef}
						onChange={handleFileUpload}
						disabled={isReadOnly || isUploading}
						accept={field.fieldtype === 'Attach Image' ? 'image/*' : undefined}
					/>
					
					{value ? (
						<div className="flex items-center gap-3 border border-line bg-panel p-2 rounded-none">
							{field.fieldtype === 'Attach Image' ? (
								<img 
									src={value as string} 
									alt="Preview" 
									className="size-10 object-cover border border-line rounded-none"
								/>
							) : (
								<div className="flex size-10 items-center justify-center bg-paper-deep border border-line rounded-none text-steel">
									<Paperclip className="size-5" />
								</div>
							)}
							<div className="min-w-0 flex-1">
								<a 
									href={value as string} 
									target="_blank" 
									rel="noopener noreferrer"
									className="truncate text-sm font-medium text-ink hover:underline block"
								>
									{(value as string).split('/').pop()}
								</a>
							</div>
							{!isReadOnly && (
								<Button
									type="button"
									variant="ghost"
									size="icon-sm"
									className="rounded-none text-steel hover:text-ink hover:bg-paper-deep"
									onClick={() => onChange('')}
								>
									<X className="size-4" />
								</Button>
							)}
						</div>
					) : (
						<Button
							type="button"
							variant="outline"
							className="rounded-none border-line bg-panel hover:bg-paper-deep text-ink w-full justify-start h-8 text-sm"
							onClick={() => fileInputRef.current?.click()}
							disabled={isReadOnly || isUploading}
						>
							{isUploading ? (
								<Loader2 className="size-4 mr-2 animate-spin" />
							) : (
								<Upload className="size-4 mr-2" />
							)}
							{isUploading ? 'Uploading...' : 'Select File'}
						</Button>
					)}
				</div>
			)}

			{field.description && field.fieldtype !== 'Check' && (
				<p className="text-[10px] text-muted-foreground">{field.description}</p>
			)}
		</div>
	);
}

