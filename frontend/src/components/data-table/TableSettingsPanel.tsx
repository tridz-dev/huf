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
import type { DataTableFieldDef } from '@/types/dataTable.types';

interface TableSettingsPanelProps {
	tableName: string;
	description: string;
	icon: string;
	autonameMethod: string;
	titleField: string;
	fields: DataTableFieldDef[];
	isEdit: boolean;
	onTableNameChange: (value: string) => void;
	onDescriptionChange: (value: string) => void;
	onIconChange: (value: string) => void;
	onAutonameMethodChange: (value: string) => void;
	onTitleFieldChange: (value: string) => void;
}

export function TableSettingsPanel({
	tableName,
	description,
	icon,
	autonameMethod,
	titleField,
	fields,
	isEdit,
	onTableNameChange,
	onDescriptionChange,
	onIconChange,
	onAutonameMethodChange,
	onTitleFieldChange,
}: TableSettingsPanelProps) {
	const dataFields = fields.filter(
		(f) => f.fieldtype !== 'Section Break' && f.fieldtype !== 'Column Break'
	);

	return (
		<div className="space-y-4">
			<div>
				<h3 className="font-medium text-sm">Table Settings</h3>
				<p className="text-xs text-muted-foreground mt-1">
					Configure your table properties
				</p>
			</div>

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

			<div className="space-y-1.5">
				<Label htmlFor="table-icon" className="text-xs">
					Icon
				</Label>
				<Select value={icon || '_none'} onValueChange={(v) => onIconChange(v === '_none' ? '' : v)}>
					<SelectTrigger className="h-8 text-sm">
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

			<div className="space-y-1.5">
				<Label htmlFor="table-autoname" className="text-xs">
					Naming Method
				</Label>
				<Select value={autonameMethod} onValueChange={onAutonameMethodChange}>
					<SelectTrigger className="h-8 text-sm">
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
				<div className="space-y-1.5">
					<Label htmlFor="table-title-field" className="text-xs">
						Title Field
					</Label>
					<Select value={titleField} onValueChange={onTitleFieldChange}>
						<SelectTrigger className="h-8 text-sm">
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
	);
}
