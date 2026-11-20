import {
	AlignLeft,
	Calendar,
	CalendarClock,
	CheckSquare,
	Clock,
	DollarSign,
	File,
	Hash,
	Image,
	Link2,
	ListFilter,
	Palette,
	Percent,
	Phone,
	Star,
	Timer,
	Columns,
	Folder,
	Minus,
	Type,
	type LucideIcon,
} from 'lucide-react';
import { TYPE_ICON, TYPE_LABEL, type ColumnTypeOption, type ColumnType } from '@/components/grid';
import type { DataTableFieldType } from '@/types/dataTable.types';

interface TypeInfo {
	label: string;
	icon: LucideIcon;
	column?: ColumnType;
	/** App-own wording/glyph that is more specific than the grid's. */
	own?: boolean;
}

const INFO: Partial<Record<DataTableFieldType, TypeInfo>> = {
	Data: { label: 'Text', icon: Type },
	'Small Text': { label: 'Long text', icon: AlignLeft, column: 'longtext' },
	Text: { label: 'Long text', icon: AlignLeft, column: 'longtext' },
	'Long Text': { label: 'Long text', icon: AlignLeft, column: 'longtext' },
	Int: { label: 'Whole number', icon: Hash, column: 'number', own: true },
	Float: { label: 'Number', icon: Hash, column: 'number', own: true },
	Currency: { label: 'Currency', icon: DollarSign, column: 'currency' },
	Percent: { label: 'Percent', icon: Percent, column: 'number', own: true },
	Check: { label: 'Checkbox', icon: CheckSquare, column: 'checkbox' },
	Date: { label: 'Date', icon: Calendar, column: 'date' },
	Datetime: { label: 'Date and time', icon: CalendarClock, column: 'date', own: true },
	Time: { label: 'Time', icon: Clock },
	Duration: { label: 'Duration', icon: Timer },
	Select: { label: 'Dropdown', icon: ListFilter, column: 'select' },
	Link: { label: 'Link to table', icon: Link2, column: 'link', own: true },
	Rating: { label: 'Rating', icon: Star, column: 'number', own: true },
	Color: { label: 'Color', icon: Palette },
	Phone: { label: 'Phone', icon: Phone },
	Attach: { label: 'File', icon: File },
	'Attach Image': { label: 'Image', icon: Image },
};

export function toColumnType(frappeType: string): ColumnType {
	return INFO[frappeType as DataTableFieldType]?.column ?? 'text';
}

export function friendlyTypeName(frappeType: string): string {
	const info = INFO[frappeType as DataTableFieldType];
	if (info?.column && !info.own) return TYPE_LABEL[info.column];
	return info?.label ?? frappeType;
}

export function typeGlyph(frappeType: string): LucideIcon {
	const info = INFO[frappeType as DataTableFieldType];
	if (info?.column && !info.own) return TYPE_ICON[info.column];
	return info?.icon ?? Type;
}

/** One entry per friendly name, for type pickers (Long text maps to Text). */
export const FRIENDLY_TYPES: Array<{ frappeType: DataTableFieldType; label: string; icon: LucideIcon }> = (
	[
		'Data', 'Text', 'Int', 'Float', 'Currency', 'Percent', 'Check', 'Date', 'Datetime',
		'Time', 'Duration', 'Select', 'Link', 'Rating', 'Color', 'Phone', 'Attach', 'Attach Image',
	] as DataTableFieldType[]
).map((t) => ({ frappeType: t, label: INFO[t]!.label, icon: INFO[t]!.icon }));

const OPTION_GROUPS: Array<{ group: string; types: Array<[DataTableFieldType, string]> }> = [
	{ group: 'Text', types: [['Data', 'A short line of text'], ['Text', 'Longer notes over several lines']] },
	{ group: 'Numbers', types: [['Int', 'Counts, no decimals'], ['Float', 'Numbers with decimals'], ['Currency', 'An amount of money'], ['Percent', 'A share out of 100']] },
	{ group: 'Date & time', types: [['Date', 'A calendar day'], ['Datetime', 'A day and a time'], ['Time', 'A time of day'], ['Duration', 'A length of time']] },
	{ group: 'Choice', types: [['Select', 'Pick one from a list you set'], ['Check', 'Yes or no'], ['Rating', 'Stars out of five']] },
	{ group: 'Reference', types: [['Link', 'Points to a row in another table']] },
	{ group: 'Other', types: [['Color', 'A color swatch'], ['Phone', 'A phone number']] },
	{ group: 'Media', types: [['Attach', 'Any file'], ['Attach Image', 'A picture']] },
];

const LAYOUT_OPTIONS: Array<ColumnTypeOption<DataTableFieldType>> = [
	{ value: 'Tab Break', label: 'Tab', icon: Folder, group: 'Layout', description: 'Starts a new tab in the form' },
	{ value: 'Section Break', label: 'Section', icon: Minus, group: 'Layout', description: 'Groups fields under a heading' },
	{ value: 'Column Break', label: 'Column', icon: Columns, group: 'Layout', description: 'Splits a section into columns' },
];

/** Options for ColumnTypePicker: plain words from this file; layout types only when not `dataOnly`. */
export function fieldTypeOptions(dataOnly = false): Array<ColumnTypeOption<DataTableFieldType>> {
	const data = OPTION_GROUPS.flatMap(({ group, types }) =>
		types.map(([value, description]) => ({ value, label: friendlyTypeName(value), icon: typeGlyph(value), group, description })),
	);
	return dataOnly ? data : [...data, ...LAYOUT_OPTIONS];
}
