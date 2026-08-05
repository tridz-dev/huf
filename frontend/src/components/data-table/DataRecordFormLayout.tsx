import { useState, useRef } from 'react';
import { Loader2, Upload, X, Paperclip, FileText as FileIcon, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
import { LinkFieldInput } from './LinkFieldInput';
import { LAYOUT_FIELD_TYPES } from '@/data/fieldTypes';
import type { DataTableFieldDef } from '@/types/dataTable.types';

export interface LayoutSection {
	label?: string;
	tabLabel?: string;
	columns: DataTableFieldDef[][];
}

const LAYOUT_DEFAULT_LABELS = new Set(['section break', 'column break']);

export function buildFormLayout(fields: DataTableFieldDef[]): LayoutSection[] {
	const sections: LayoutSection[] = [{ columns: [[]] }];
	for (const field of fields) {
		if (field.fieldtype === 'Tab Break') {
			const raw = field.label?.trim();
			sections.push({ tabLabel: raw || undefined, columns: [[]] });
		} else if (field.fieldtype === 'Section Break') {
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
		if (LAYOUT_FIELD_TYPES.includes(field.fieldtype)) continue;
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
				headers: { Accept: 'application/json' },
			});

			if (!response.ok) throw new Error('Upload failed');
			const data = await response.json();
			if (data.message?.file_url) onChange(data.message.file_url);
		} catch (error) {
			console.error(error);
		} finally {
			setIsUploading(false);
			if (fileInputRef.current) fileInputRef.current.value = '';
		}
	};

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
								size="sm" className="border-line"
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
								className="text-sm rounded border-line"
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
								size="sm" className="border-line"
							/>
						) : field.fieldtype === 'Check' ? (
							<div className="flex items-center gap-2 pt-1">
								<Checkbox
									checked={value === 1 || value === true}
									onCheckedChange={(checked) => onChange(checked ? 1 : 0)}
									disabled={isReadOnly}
									className="rounded border-line"
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
								size="sm" className="border-line"
							/>
						) : field.fieldtype === 'Time' ? (
							<Input
								type="time"
								value={(value as string) || ''}
								onChange={(event) => onChange(event.target.value)}
								disabled={isReadOnly}
								size="sm" className="border-line"
							/>
						) : field.fieldtype === 'Duration' ? (
							<Input
								type="text"
								value={(value as string) || ''}
								onChange={(event) => onChange(event.target.value)}
								disabled={isReadOnly}
								placeholder="e.g. 1h 30m"
								size="sm" className="border-line"
							/>
						) : field.fieldtype === 'Select' ? (
							<Select
								value={(value as string) || ''}
								onValueChange={onChange}
								disabled={isReadOnly}
							>
								<SelectTrigger size="sm" className="border-line">
									<SelectValue placeholder="Select..." />
								</SelectTrigger>
								<SelectContent className="rounded border-line">
									{(field.options || '')
										.split('\n')
										.filter(Boolean)
										.map((option) => (
											<SelectItem key={option} value={option} className="rounded">
												{option}
											</SelectItem>
										))}
								</SelectContent>
							</Select>
		) : field.fieldtype === 'Link' ? (
			<LinkFieldInput
				targetDoctype={field.options}
				value={(value as string) || ''}
				onChange={onChange}
				disabled={isReadOnly}
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
								size="sm" className="border-line"
							/>
						) : field.fieldtype === 'Color' ? (
							<Input
								type="color"
								value={(value as string) || undefined}
								onChange={(event) => onChange(event.target.value)}
								disabled={isReadOnly}
								className="h-8 w-16 rounded border-line p-1"
							/>
						) : ((field.fieldtype as string) === 'Attach' || (field.fieldtype as string) === 'Attach Image') ? (
							<div className="space-y-2">
								<input
									type="file"
									className="hidden"
									ref={fileInputRef}
									onChange={handleFileUpload}
									disabled={isReadOnly || isUploading}
									accept={(field.fieldtype as string) === 'Attach Image' ? 'image/*' : undefined}
								/>
								{value ? (
									<div className="flex items-center gap-3 border border-line bg-panel p-2 rounded">
										{(field.fieldtype as string) === 'Attach Image' ? (
											<img src={value as string} alt="Preview" className="size-10 object-cover border border-line rounded" />
										) : (
											<div className="flex size-10 items-center justify-center bg-paper-deep border border-line rounded text-steel">
												<Paperclip className="size-5" />
											</div>
										)}
										<div className="min-w-0 flex-1">
											<a href={value as string} target="_blank" rel="noopener noreferrer" className="truncate text-sm font-medium text-ink hover:underline block">
												{(value as string).split('/').pop()}
											</a>
										</div>
										{!isReadOnly && (
											<Button type="button" variant="ghost" size="icon-sm" className="rounded text-steel hover:text-ink hover:bg-paper-deep" onClick={() => onChange('')}>
												<X className="size-4" />
											</Button>
										)}
									</div>
								) : (
									<Button type="button" variant="outline" className="rounded border-line bg-panel hover:bg-paper-deep text-ink w-full justify-start h-8 text-sm" onClick={() => fileInputRef.current?.click()} disabled={isReadOnly || isUploading}>
										{isUploading ? <Loader2 className="size-4 mr-2 animate-spin" /> : <Upload className="size-4 mr-2" />}
										{isUploading ? 'Uploading...' : 'Select File'}
									</Button>
								)}
							</div>
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

const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'avif'];
const VIDEO_EXTENSIONS = ['mp4', 'webm', 'ogg', 'mov'];

function getFileExtension(url: string): string {
	const withoutQuery = url.split('?')[0];
	const parts = withoutQuery.split('.');
	return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : '';
}

function getFileName(url: string): string {
	const withoutQuery = url.split('?')[0];
	const parts = withoutQuery.split('/');
	return parts[parts.length - 1] || url;
}

/** Renders an Attach/Attach Image field's stored file URL as an image thumbnail, an
 * inline video player, or a generic file link — based on the file's extension, since
 * `Attach` can hold any file type while `Attach Image` is always an image. */
function AttachFieldView({ fieldtype, value }: { fieldtype: string; value: unknown }) {
	const url = typeof value === 'string' ? value : '';
	if (!url) {
		return <span className="text-steel-soft italic text-sm">Empty</span>;
	}

	const ext = getFileExtension(url);
	const isImage = fieldtype === 'Attach Image' || IMAGE_EXTENSIONS.includes(ext);
	const isVideo = !isImage && VIDEO_EXTENSIONS.includes(ext);

	if (isImage) {
		return (
			<a href={url} target="_blank" rel="noreferrer" className="inline-block">
				<img
					src={url}
					alt={getFileName(url)}
					className="max-h-48 rounded border border-line object-contain"
				/>
			</a>
		);
	}

	if (isVideo) {
		return (
			<video
				src={url}
				controls
				className="max-h-64 max-w-full rounded border border-line"
			>
				Your browser does not support video playback.
			</video>
		);
	}

	return (
		<a
			href={url}
			target="_blank"
			rel="noreferrer"
			className="inline-flex items-center gap-2 px-3 py-1.5 rounded border border-line bg-panel text-sm text-ink hover:bg-paper-deep"
		>
			<FileIcon className="w-4 h-4 text-steel shrink-0" />
			<span className="truncate max-w-xs">{getFileName(url)}</span>
			<ExternalLink className="w-3.5 h-3.5 text-steel shrink-0" />
		</a>
	);
}

export function FieldView({ field, value }: { field: DataTableFieldDef, value: unknown }) {
    let displayValue: React.ReactNode = String(value ?? '');
    
    if (field.fieldtype === 'Check') {
        const isChecked = value === 1 || value === true;
        displayValue = isChecked ? (
            <span className="inline-flex items-center px-2 py-0.5 rounded border border-line bg-paper-deep text-xs font-medium text-ink">Yes</span>
        ) : (
            <span className="inline-flex items-center px-2 py-0.5 rounded border border-line bg-panel text-xs font-medium text-steel">No</span>
        );
    } else if (field.fieldtype === 'Select' || field.fieldtype === 'Link') {
        if (value) {
            displayValue = (
                <span className="inline-flex items-center px-2 py-0.5 rounded border border-line bg-paper-deep text-sm font-medium text-ink">
                    {String(value)}
                </span>
            );
        } else {
            displayValue = <span className="text-steel-soft italic text-sm">Empty</span>;
        }
    } else if (field.fieldtype === 'Text' || field.fieldtype === 'Small Text' || field.fieldtype === 'Long Text') {
        displayValue = value ? (
            <div className="whitespace-pre-wrap text-sm text-ink bg-paper-deep p-3 border border-line rounded">
                {String(value)}
            </div>
        ) : (
            <span className="text-steel-soft italic text-sm">Empty</span>
        );
    } else if ((field.fieldtype as string) === 'Attach' || (field.fieldtype as string) === 'Attach Image') {
        displayValue = <AttachFieldView fieldtype={field.fieldtype} value={value} />;
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
