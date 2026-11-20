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
	Type,
	type LucideIcon,
} from 'lucide-react';
import type { DataTableFieldType } from '@/types/dataTable.types';

/** Column types understood by the DataGrid. */
export type GridColumnType = 'text' | 'number' | 'date' | 'select' | 'check' | 'longtext' | 'link';

interface TypeInfo {
	label: string;
	icon: LucideIcon;
	grid: GridColumnType;
}

const INFO: Partial<Record<DataTableFieldType, TypeInfo>> = {
	Data: { label: 'Text', icon: Type, grid: 'text' },
	'Small Text': { label: 'Long text', icon: AlignLeft, grid: 'longtext' },
	Text: { label: 'Long text', icon: AlignLeft, grid: 'longtext' },
	'Long Text': { label: 'Long text', icon: AlignLeft, grid: 'longtext' },
	Int: { label: 'Whole number', icon: Hash, grid: 'number' },
	Float: { label: 'Number', icon: Hash, grid: 'number' },
	Currency: { label: 'Currency', icon: DollarSign, grid: 'number' },
	Percent: { label: 'Percent', icon: Percent, grid: 'number' },
	Check: { label: 'Checkbox', icon: CheckSquare, grid: 'check' },
	Date: { label: 'Date', icon: Calendar, grid: 'date' },
	Datetime: { label: 'Date and time', icon: CalendarClock, grid: 'date' },
	Time: { label: 'Time', icon: Clock, grid: 'text' },
	Duration: { label: 'Duration', icon: Timer, grid: 'text' },
	Select: { label: 'Dropdown', icon: ListFilter, grid: 'select' },
	Link: { label: 'Link to table', icon: Link2, grid: 'link' },
	Rating: { label: 'Rating', icon: Star, grid: 'number' },
	Color: { label: 'Color', icon: Palette, grid: 'text' },
	Phone: { label: 'Phone', icon: Phone, grid: 'text' },
	Attach: { label: 'File', icon: File, grid: 'text' },
	'Attach Image': { label: 'Image', icon: Image, grid: 'text' },
};

export function friendlyTypeName(frappeType: string): string {
	return INFO[frappeType as DataTableFieldType]?.label ?? frappeType;
}

export function typeGlyph(frappeType: string): LucideIcon {
	return INFO[frappeType as DataTableFieldType]?.icon ?? Type;
}

export function gridColumnType(frappeType: string): GridColumnType {
	return INFO[frappeType as DataTableFieldType]?.grid ?? 'text';
}

/** One entry per friendly name, for type pickers (Long text maps to Text). */
export const FRIENDLY_TYPES: Array<{ frappeType: DataTableFieldType; label: string; icon: LucideIcon }> = (
	[
		'Data', 'Text', 'Int', 'Float', 'Currency', 'Percent', 'Check', 'Date', 'Datetime',
		'Time', 'Duration', 'Select', 'Link', 'Rating', 'Color', 'Phone', 'Attach', 'Attach Image',
	] as DataTableFieldType[]
).map((t) => ({ frappeType: t, label: INFO[t]!.label, icon: INFO[t]!.icon }));
