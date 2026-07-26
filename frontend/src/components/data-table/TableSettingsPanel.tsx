import { useEffect, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@/components/ui/select';
import { TABLE_ICONS, TABLE_ICON_MAP } from '@/data/tableIcons';
import { getTableGroups } from '@/services/dataTableApi';
import type { DataTableFieldDef } from '@/types/dataTable.types';

interface TableSettingsPanelProps {
	tableName: string;
	description: string;
	icon: string;
	autonameMethod: string;
	titleField: string;
	tableGroup: string;
	fields: DataTableFieldDef[];
	isEdit: boolean;
	onTableNameChange: (value: string) => void;
	onDescriptionChange: (value: string) => void;
	onIconChange: (value: string) => void;
	onAutonameMethodChange: (value: string) => void;
	onTitleFieldChange: (value: string) => void;
	onTableGroupChange: (value: string) => void;
}

export function TableSettingsPanel({
	tableName,
	description,
	icon,
	autonameMethod,
	titleField,
	tableGroup,
	fields,
	isEdit,
	onTableNameChange,
	onDescriptionChange,
	onIconChange,
	onAutonameMethodChange,
	onTitleFieldChange,
	onTableGroupChange,
}: TableSettingsPanelProps) {
	const dataFields = fields.filter(
		(f) => f.fieldtype !== 'Section Break' && f.fieldtype !== 'Column Break'
	);

	const [existingGroups, setExistingGroups] = useState<string[]>([]);
	useEffect(() => {
		getTableGroups().then(setExistingGroups);
	}, []);

	return (
		<div className="space-y-4">
			<div>
				<h3 className="font-medium text-sm">Table Settings</h3>
				<p className="text-xs text-steel-soft mt-1">
					Configure your table properties
				</p>
			</div>

			{/* Primary fields — what the table is */}
			<div className="space-y-1.5">
				<Label htmlFor="table-name" className="text-xs">
					Table Name *
				</Label>
				<Input
					id="table-name"
					value={tableName}
					onChange={(e) => onTableNameChange(e.target.value)}
					placeholder="e.g. Products, Contacts"
					className="h-8 text-sm"
					disabled={isEdit}
				/>
			</div>

			<div className="space-y-1.5">
				<Label htmlFor="table-description" className="text-xs">
					Description
				</Label>
				<Textarea
					id="table-description"
					value={description}
					onChange={(e) => onDescriptionChange(e.target.value)}
					placeholder="What is this table for?"
					rows={3}
					className="text-sm"
				/>
			</div>

			{/* Additional Settings — secondary/organizational metadata, most tables never
			    touch these beyond their defaults, so they get less visual weight and sit
			    below the fields that define what the table actually is. */}
			<div className="space-y-3 pt-2 border-t border-line">
				<h4 className="text-xs font-medium text-steel-soft uppercase tracking-wide">
					Additional Settings
				</h4>

				<div className="space-y-1">
					<Label htmlFor="table-group" className="text-xs text-steel">
						Group
					</Label>
					<Input
						id="table-group"
						value={tableGroup}
						onChange={(e) => onTableGroupChange(e.target.value)}
						placeholder="e.g. Customers"
						className="h-7 text-xs"
						list="existing-table-groups"
						autoComplete="off"
					/>
					<datalist id="existing-table-groups">
						{existingGroups.map((g) => (
							<option key={g} value={g} />
						))}
					</datalist>
					{existingGroups.length > 0 && (
						<p className="text-[10px] text-steel-soft">
							Existing groups: {existingGroups.join(', ')}
						</p>
					)}
				</div>

				<div className="space-y-1">
					<Label htmlFor="table-icon" className="text-xs text-steel">
						Icon
					</Label>
					<Select value={icon || '_none'} onValueChange={(v) => onIconChange(v === '_none' ? '' : v)}>
						<SelectTrigger className="h-7 text-xs">
							{icon && TABLE_ICON_MAP[icon] ? (
								<div className="flex items-center gap-2 justify-start w-full">
									{(() => {
										const Icon = TABLE_ICON_MAP[icon];
										return <Icon className="w-3.5 h-3.5" />;
									})()}
									{TABLE_ICONS.find((i) => i.name === icon)?.label ?? icon}
								</div>
							) : (
								<SelectValue placeholder="Select an icon" />
							)}
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="_none">No icon</SelectItem>
							{TABLE_ICONS.map((entry) => (
								<SelectItem key={entry.name} value={entry.name}>
									<span className="flex items-center gap-2">
										<entry.icon className="w-3.5 h-3.5" />
										{entry.label}
									</span>
								</SelectItem>
							))}
						</SelectContent>
					</Select>
				</div>

				<div className="space-y-1">
					<Label htmlFor="table-autoname" className="text-xs text-steel">
						Naming Method
					</Label>
					<Select value={autonameMethod} onValueChange={onAutonameMethodChange}>
						<SelectTrigger className="h-7 text-xs">
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="Autoincrement">Auto-increment (1, 2, 3...)</SelectItem>
							<SelectItem value="Hash">Random Hash</SelectItem>
							<SelectItem value="By Field">By Field Value</SelectItem>
						</SelectContent>
					</Select>
				</div>

				{autonameMethod === 'By Field' && (
					<div className="space-y-1">
						<Label htmlFor="table-title-field" className="text-xs text-steel">
							Title Field
						</Label>
						<Select value={titleField} onValueChange={onTitleFieldChange}>
							<SelectTrigger className="h-7 text-xs">
								<SelectValue placeholder="Select a field" />
							</SelectTrigger>
							<SelectContent>
								{dataFields.map((f) => (
									<SelectItem key={f.fieldname} value={f.fieldname}>
										{f.label}
									</SelectItem>
								))}
							</SelectContent>
						</Select>
					</div>
				)}
			</div>
		</div>
	);
}
