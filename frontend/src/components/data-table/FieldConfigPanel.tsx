import { useEffect, useState } from 'react';
import { Settings, Trash2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@/components/ui/select';
import { FIELD_PROPERTIES, LAYOUT_FIELD_TYPES } from '@/data/fieldTypes';
import { getHufTableNames } from '@/services/dataTableApi';
import type { DataTableFieldDef } from '@/types/dataTable.types';

interface FieldConfigPanelProps {
	field: DataTableFieldDef;
	onUpdate: (updates: Partial<DataTableFieldDef>) => void;
	onDelete: () => void;
	onOpenTableSettings: () => void;
}

export function FieldConfigPanel({
	field,
	onUpdate,
	onDelete,
	onOpenTableSettings,
}: FieldConfigPanelProps) {
	const [hufTables, setHufTables] = useState<Array<{ table_name: string; doctype_name: string }>>(
		[]
	);

	const properties = FIELD_PROPERTIES[field.fieldtype] || [];
	const isLayout = LAYOUT_FIELD_TYPES.includes(field.fieldtype as any);

	useEffect(() => {
		if (field.fieldtype === 'Link') {
			getHufTableNames()
				.then(setHufTables)
				.catch(() => setHufTables([]));
		}
	}, [field.fieldtype]);

	const reservedFieldnames = new Set([
		'name', 'doctype', 'owner', 'creation', 'modified',
		'modified_by', 'docstatus', 'idx', 'parent', 'parentfield', 'parenttype',
	]);

	const handleLabelChange = (label: string) => {
		let fieldname = label
			.toLowerCase()
			.replace(/[^a-z0-9\s]/g, '')
			.replace(/\s+/g, '_')
			.replace(/_+/g, '_')
			.replace(/^_|_$/g, '');
		if (reservedFieldnames.has(fieldname)) {
			fieldname = `${fieldname}_field`;
		}
		onUpdate({ label, fieldname: fieldname || field.fieldname });
	};

	return (
		<div className="space-y-4">
			<div className="flex items-center justify-between">
				<div>
					<h3 className="font-medium text-sm">
						{isLayout ? field.fieldtype : 'Field Properties'}
					</h3>
					<p className="text-xs text-muted-foreground mt-1">
						{isLayout ? 'Layout element settings' : field.fieldtype}
					</p>
				</div>
				<Button
					variant="ghost"
					size="icon"
					className="h-7 w-7 text-muted-foreground"
					onClick={onOpenTableSettings}
					title="Open table settings"
				>
					<Settings className="w-3.5 h-3.5" />
				</Button>
			</div>

			<Separator />

			{properties.includes('label') && (
				<div className="space-y-1.5">
					<Label htmlFor="field-label" className="text-xs">
						Label
					</Label>
					<Input
						id="field-label"
						value={field.label || ''}
						onChange={(e) => handleLabelChange(e.target.value)}
						placeholder="Field label"
						className="h-8 text-sm"
					/>
					{!isLayout && (
						<p className="text-[10px] text-muted-foreground">
							Name: {field.fieldname}
						</p>
					)}
				</div>
			)}

			{properties.includes('options') && field.fieldtype === 'Select' && (
				<div className="space-y-1.5">
					<Label htmlFor="field-options" className="text-xs">
						Options (one per line)
					</Label>
					<Textarea
						id="field-options"
						value={field.options || ''}
						onChange={(e) => onUpdate({ options: e.target.value })}
						placeholder={"Option 1\nOption 2\nOption 3"}
						rows={4}
						className="text-sm"
					/>
				</div>
			)}

			{properties.includes('options') && field.fieldtype === 'Link' && (
				<div className="space-y-1.5">
					<Label htmlFor="field-link-target" className="text-xs">
						Link Target
					</Label>
					<Select
						value={field.options || ''}
						onValueChange={(value) => onUpdate({ options: value })}
					>
						<SelectTrigger className="h-8 text-sm">
							<SelectValue placeholder="Select a table" />
						</SelectTrigger>
						<SelectContent>
							{hufTables.map((t) => (
								<SelectItem key={t.doctype_name} value={t.doctype_name}>
									{t.table_name}
								</SelectItem>
							))}
						</SelectContent>
					</Select>
				</div>
			)}

			{properties.includes('default') && (
				<div className="space-y-1.5">
					<Label htmlFor="field-default" className="text-xs">
						Default Value
					</Label>
					<Input
						id="field-default"
						value={field.default || ''}
						onChange={(e) => onUpdate({ default: e.target.value })}
						placeholder="Default value"
						className="h-8 text-sm"
					/>
				</div>
			)}

			{properties.includes('description') && (
				<div className="space-y-1.5">
					<Label htmlFor="field-description" className="text-xs">
						Help Text
					</Label>
					<Input
						id="field-description"
						value={field.description || ''}
						onChange={(e) => onUpdate({ description: e.target.value })}
						placeholder="Help text shown below field"
						className="h-8 text-sm"
					/>
				</div>
			)}

			{!isLayout && (
				<div className="space-y-3">
					<Separator />
					<p className="text-xs font-medium text-muted-foreground">Properties</p>

					{properties.includes('reqd') && (
						<div className="flex items-center gap-2">
							<Checkbox
								id="field-reqd"
								checked={field.reqd === 1}
								onCheckedChange={(checked) =>
									onUpdate({ reqd: checked ? 1 : 0 })
								}
							/>
							<Label htmlFor="field-reqd" className="text-xs font-normal">
								Required
							</Label>
						</div>
					)}

					{properties.includes('unique') && (
						<div className="flex items-center gap-2">
							<Checkbox
								id="field-unique"
								checked={field.unique === 1}
								onCheckedChange={(checked) =>
									onUpdate({ unique: checked ? 1 : 0 })
								}
							/>
							<Label htmlFor="field-unique" className="text-xs font-normal">
								Unique
							</Label>
						</div>
					)}

					{properties.includes('read_only') && (
						<div className="flex items-center gap-2">
							<Checkbox
								id="field-read-only"
								checked={field.read_only === 1}
								onCheckedChange={(checked) =>
									onUpdate({ read_only: checked ? 1 : 0 })
								}
							/>
							<Label htmlFor="field-read-only" className="text-xs font-normal">
								Read Only
							</Label>
						</div>
					)}

					{properties.includes('in_list_view') && (
						<div className="flex items-center gap-2">
							<Checkbox
								id="field-in-list-view"
								checked={field.in_list_view === 1}
								onCheckedChange={(checked) =>
									onUpdate({ in_list_view: checked ? 1 : 0 })
								}
							/>
							<Label htmlFor="field-in-list-view" className="text-xs font-normal">
								Show in List View
							</Label>
						</div>
					)}

					{properties.includes('non_negative') && (
						<div className="flex items-center gap-2">
							<Checkbox
								id="field-non-negative"
								checked={field.non_negative === 1}
								onCheckedChange={(checked) =>
									onUpdate({ non_negative: checked ? 1 : 0 })
								}
							/>
							<Label htmlFor="field-non-negative" className="text-xs font-normal">
								Non-negative only
							</Label>
						</div>
					)}
				</div>
			)}

			<Separator />

			<Button
				variant="destructive"
				size="sm"
				className="w-full"
				onClick={onDelete}
			>
				<Trash2 className="w-3.5 h-3.5 mr-2" />
				Delete Field
			</Button>
		</div>
	);
}
