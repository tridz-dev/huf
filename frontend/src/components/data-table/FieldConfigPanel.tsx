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
	const isLayout = LAYOUT_FIELD_TYPES.includes(field.fieldtype);

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
			<div className="sticky top-0 z-10 bg-panel border-b border-line pb-3 -mx-1 px-1 mb-4 flex items-center justify-between">
				<div>
					<h3 className="font-medium text-sm">
						{isLayout ? field.fieldtype : 'Field properties'}
					</h3>
					<p className="text-xs text-steel mt-1">
						{isLayout ? 'Layout element settings' : field.fieldtype}
					</p>
				</div>
				<Button
					variant="ghost"
					size="icon"
					className="h-7 w-7 text-steel"
					onClick={onOpenTableSettings}
					title="Open table settings"
				>
					<Settings className="w-3.5 h-3.5" />
				</Button>
			</div>

			{properties.includes('label') && (
				<div className="space-y-1.5">
					<Label htmlFor="field-label" size="sm">
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
						<p className="text-[10px] text-steel">
							Name: {field.fieldname}
						</p>
					)}
				</div>
			)}

			{properties.includes('options') && field.fieldtype === 'Select' && (
				<div className="space-y-1.5">
					<Label htmlFor="field-options" size="sm">
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
					<Label htmlFor="field-link-target" size="sm">
						Link target
					</Label>
					<Select
						value={field.options || ''}
						onValueChange={(value) => onUpdate({ options: value })}
					>
						<SelectTrigger size="sm">
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

			{(properties.includes('default') || properties.includes('description')) && (
				<div className="space-y-3 pt-2 border-t border-line">
					<h4 className="text-xs font-medium text-steel-soft uppercase tracking-wide">
						Additional settings
					</h4>

					{properties.includes('default') && (
						<div className="space-y-1">
							<Label htmlFor="field-default" size="sm" tone="muted">
								Default value
							</Label>
							<Input
								id="field-default"
								value={field.default || ''}
								onChange={(e) => onUpdate({ default: e.target.value })}
								placeholder="Default value"
								className="h-7 text-xs"
							/>
						</div>
					)}

					{properties.includes('description') && (
						<div className="space-y-1">
							<Label htmlFor="field-description" size="sm" tone="muted">
								Help text
							</Label>
							<Input
								id="field-description"
								value={field.description || ''}
								onChange={(e) => onUpdate({ description: e.target.value })}
								placeholder="Help text shown below field"
								className="h-7 text-xs"
							/>
						</div>
					)}
				</div>
			)}

			{!isLayout && (
				<div className="space-y-3">
					<Separator />
					<p className="text-xs font-medium text-steel">Properties</p>

					{properties.includes('reqd') && (
						<div className="flex items-center gap-2">
							<Checkbox
								id="field-reqd"
								checked={field.reqd === 1}
								onCheckedChange={(checked) =>
									onUpdate({ reqd: checked ? 1 : 0 })
								}
							/>
							<Label htmlFor="field-reqd" size="sm" weight="normal">
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
							<Label htmlFor="field-unique" size="sm" weight="normal">
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
							<Label htmlFor="field-read-only" size="sm" weight="normal">
								Read only
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
							<Label htmlFor="field-in-list-view" size="sm" weight="normal">
								Show in list view
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
							<Label htmlFor="field-non-negative" size="sm" weight="normal">
								Non-negative only
							</Label>
						</div>
					)}
				</div>
			)}

			<div className="pt-4 border-t border-line mt-4 flex items-center justify-between gap-2">
				<p className="text-[10px] text-steel">
					Changes save with the table.
				</p>
				<Button
					variant="ghost"
					size="sm"
					className="text-destructive hover:text-destructive hover:bg-destructive/10"
					onClick={onDelete}
				>
					<Trash2 className="w-3.5 h-3.5 mr-1.5" />
					Delete field
				</Button>
			</div>
		</div>
	);
}
