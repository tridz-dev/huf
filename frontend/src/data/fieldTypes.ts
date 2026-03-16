import type { DataTableFieldType } from '@/types/dataTable.types';

export interface FieldTypeGroup {
	label: string;
	types: FieldTypeDef[];
}

export interface FieldTypeDef {
	type: DataTableFieldType;
	label: string;
	icon: string;
	description: string;
}

export const FIELD_TYPE_GROUPS: FieldTypeGroup[] = [
	{
		label: 'Text',
		types: [
			{ type: 'Data', label: 'Short Text', icon: 'Type', description: 'Single line text' },
			{
				type: 'Small Text',
				label: 'Medium Text',
				icon: 'FileText',
				description: 'Multi-line text',
			},
			{ type: 'Text', label: 'Long Text', icon: 'AlignLeft', description: 'Large text area' },
		],
	},
	{
		label: 'Numbers',
		types: [
			{ type: 'Int', label: 'Integer', icon: 'Hash', description: 'Whole number' },
			{ type: 'Float', label: 'Decimal', icon: 'Hash', description: 'Decimal number' },
			{
				type: 'Currency',
				label: 'Currency',
				icon: 'DollarSign',
				description: 'Money amount',
			},
			{ type: 'Percent', label: 'Percent', icon: 'Percent', description: 'Percentage value' },
		],
	},
	{
		label: 'Date & Time',
		types: [
			{ type: 'Date', label: 'Date', icon: 'Calendar', description: 'Date picker' },
			{
				type: 'Datetime',
				label: 'Date & Time',
				icon: 'CalendarClock',
				description: 'Date and time',
			},
			{ type: 'Time', label: 'Time', icon: 'Clock', description: 'Time only' },
			{ type: 'Duration', label: 'Duration', icon: 'Timer', description: 'Time duration' },
		],
	},
	{
		label: 'Choice',
		types: [
			{
				type: 'Select',
				label: 'Dropdown',
				icon: 'ChevronDown',
				description: 'Select from options',
			},
			{ type: 'Check', label: 'Checkbox', icon: 'CheckSquare', description: 'True/false' },
			{ type: 'Rating', label: 'Rating', icon: 'Star', description: 'Star rating' },
		],
	},
	{
		label: 'Reference',
		types: [
			{
				type: 'Link',
				label: 'Link to Table',
				icon: 'Link2',
				description: 'Reference another table',
			},
		],
	},
	{
		label: 'Other',
		types: [
			{ type: 'Color', label: 'Color', icon: 'Palette', description: 'Color picker' },
			{ type: 'Phone', label: 'Phone', icon: 'Phone', description: 'Phone number' },
		],
	},
	{
		label: 'Layout',
		types: [
			{
				type: 'Section Break',
				label: 'Section',
				icon: 'Minus',
				description: 'Group fields into a section',
			},
			{
				type: 'Column Break',
				label: 'Column',
				icon: 'Columns',
				description: 'Split section into columns',
			},
		],
	},
];

/**
 * Properties applicable to each field type
 */
export const FIELD_PROPERTIES: Record<string, string[]> = {
	Data: ['label', 'reqd', 'unique', 'read_only', 'default', 'description', 'in_list_view'],
	'Small Text': ['label', 'reqd', 'read_only', 'default', 'description', 'in_list_view'],
	Text: ['label', 'reqd', 'read_only', 'default', 'description', 'in_list_view'],
	'Long Text': ['label', 'reqd', 'read_only', 'default', 'description'],
	Int: [
		'label',
		'reqd',
		'unique',
		'read_only',
		'default',
		'description',
		'in_list_view',
		'non_negative',
	],
	Float: [
		'label',
		'reqd',
		'unique',
		'read_only',
		'default',
		'description',
		'in_list_view',
		'non_negative',
	],
	Currency: [
		'label',
		'reqd',
		'read_only',
		'default',
		'description',
		'in_list_view',
		'non_negative',
	],
	Percent: [
		'label',
		'reqd',
		'read_only',
		'default',
		'description',
		'in_list_view',
		'non_negative',
	],
	Check: ['label', 'read_only', 'default', 'description', 'in_list_view'],
	Date: ['label', 'reqd', 'read_only', 'default', 'description', 'in_list_view'],
	Datetime: ['label', 'reqd', 'read_only', 'default', 'description', 'in_list_view'],
	Time: ['label', 'reqd', 'read_only', 'default', 'description', 'in_list_view'],
	Duration: ['label', 'reqd', 'read_only', 'default', 'description', 'in_list_view'],
	Select: ['label', 'reqd', 'read_only', 'default', 'options', 'description', 'in_list_view'],
	Link: ['label', 'reqd', 'read_only', 'options', 'description', 'in_list_view'],
	Rating: ['label', 'read_only', 'description', 'in_list_view'],
	Color: ['label', 'reqd', 'read_only', 'description', 'in_list_view'],
	Phone: ['label', 'reqd', 'unique', 'read_only', 'default', 'description', 'in_list_view'],
	'Section Break': ['label'],
	'Column Break': [],
};

export const LAYOUT_FIELD_TYPES: DataTableFieldType[] = ['Section Break', 'Column Break'];
