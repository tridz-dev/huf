import { useEffect, useState } from 'react';
import { Settings, Trash2 } from 'lucide-react';
import { ChangeImpactNotice } from '@/components/grid';
import { Field } from '@/components/ui/field';
import { FieldTypeSelector } from './FieldTypeSelector';
import { deriveFieldname, type FieldErrors } from './builder/fieldRules';
import { friendlyTypeName, typeGlyph } from '@/data/fieldTypeLabels';
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
import type { DataTableFieldDef, DataTableFieldType } from '@/types/dataTable.types';

interface FieldConfigPanelProps {
	field: DataTableFieldDef;
	onUpdate: (updates: Partial<DataTableFieldDef>) => void;
	onDelete: () => void;
	onOpenTableSettings: () => void;
	/** The field already exists in the saved table: fieldname is locked, type change needs confirm. */
	isExisting?: boolean;
	/** Fieldnames of the other fields, so new names stay unique. */
	otherFieldnames?: string[];
	errors?: FieldErrors;
}

export function FieldConfigPanel({
	field,
	onUpdate,
	onDelete,
	onOpenTableSettings,
	isExisting = false,
	otherFieldnames = [],
	errors,
}: FieldConfigPanelProps) {
	const [pendingType, setPendingType] = useState<DataTableFieldType | null>(null);
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

	const handleLabelChange = (label: string) => {
		// DATA-LOSS GUARD: an existing field's fieldname is its column. Only the label changes.
		if (isExisting) {
			onUpdate({ label });
			return;
		}
		onUpdate({ label, fieldname: deriveFieldname(label, new Set(otherFieldnames), field.fieldname) });
	};

	const handleTypePick = (type: DataTableFieldType) => {
		if (type === field.fieldtype) return;
		if (isExisting) setPendingType(type);
		else onUpdate({ fieldtype: type });
	};

	return (
		<div className="space-y-4">
			<div className="sticky top-0 z-10 bg-panel border-b border-line pb-3 -mx-1 px-1 mb-4 flex items-center justify-between">
				<div>
					<h3 className="font-medium text-sm">
						{isLayout ? friendlyTypeName(field.fieldtype) : 'Field properties'}
					</h3>
					<p className="text-xs text-steel mt-1">
						{isLayout ? 'Layout element settings' : friendlyTypeName(field.fieldtype)}
					</p>
				</div>
				<Button
					variant="ghost"
					size="icon"
					className="text-steel" aria-label="Open table settings"
					onClick={onOpenTableSettings}
					title="Open table settings"
				>
					<Settings className="w-3.5 h-3.5" />
				</Button>
			</div>

			{properties.includes('label') && (
				<Field label="Label" required={!isLayout} error={errors?.label} id="field-label">
					{(c) => (
						<Input
							{...c}
							value={field.label || ''}
							onChange={(e) => handleLabelChange(e.target.value)}
							placeholder="Field label"
						/>
					)}
				</Field>
			)}

			{!isLayout && (
				<div className="space-y-2">
					<p className="text-xs font-medium text-ink">Type</p>
					<FieldTypeSelector
						dataOnly
						value={field.fieldtype}
						onSelect={handleTypePick}
						trigger={
							<Button variant="outline" size="sm" className="w-full justify-start gap-2">
								{(() => {
									const Icon = typeGlyph(field.fieldtype);
									return <Icon aria-hidden="true" className="w-4 h-4 text-steel" />;
								})()}
								{friendlyTypeName(field.fieldtype)}
							</Button>
						}
					/>
					{pendingType && (
						// TODO(P3): once a type-change preview endpoint exists, pass real counts as `lines`
						// (e.g. "1,180 values convert", "104 will be cleared"). Until then the wording is
						// generic and no endpoint is called.
						<ChangeImpactNotice
							title={`Change ${friendlyTypeName(field.fieldtype)} to ${friendlyTypeName(pendingType)}?`}
							action={
								<div className="space-y-2">
									<p className="text-micro text-steel">Existing values may be converted or cleared. This applies when you save changes.</p>
									<div className="flex gap-2">
										<Button
											size="sm"
											variant="destructive"
											onClick={() => {
												onUpdate({ fieldtype: pendingType });
												setPendingType(null);
											}}
										>
											Change type
										</Button>
										<Button size="sm" variant="ghost" onClick={() => setPendingType(null)}>
											Keep {friendlyTypeName(field.fieldtype)}
										</Button>
									</div>
								</div>
							}
						/>
					)}
				</div>
			)}

			{properties.includes('options') && field.fieldtype === 'Select' && (
				<Field label="Options (one per line)" required error={errors?.options} id="field-options">
					{(c) => (
						<Textarea
							{...c}
							value={field.options || ''}
							onChange={(e) => onUpdate({ options: e.target.value })}
							placeholder={"Option 1\nOption 2\nOption 3"}
							rows={4}
						/>
					)}
				</Field>
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
				<p className="text-micro text-steel">
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
