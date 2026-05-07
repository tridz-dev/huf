import {
	Type,
	FileText,
	AlignLeft,
	Hash,
	DollarSign,
	Percent,
	Calendar,
	CalendarClock,
	Clock,
	Timer,
	ChevronDown,
	CheckSquare,
	Star,
	Link2,
	Palette,
	Phone,
	Minus,
	Columns,
	LucideIcon,
} from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import type { DataTableFieldType } from '@/types/dataTable.types';

const ICON_MAP: Record<string, LucideIcon> = {
	Type,
	FileText,
	AlignLeft,
	Hash,
	DollarSign,
	Percent,
	Calendar,
	CalendarClock,
	Clock,
	Timer,
	ChevronDown,
	CheckSquare,
	Star,
	Link2,
	Palette,
	Phone,
	Minus,
	Columns,
};

interface FieldTypeGroup {
	label: string;
	types: { type: DataTableFieldType; label: string; icon: string }[];
}

const GROUPS: FieldTypeGroup[] = [
	{
		label: 'Text',
		types: [
			{ type: 'Data', label: 'Short Text', icon: 'Type' },
			{ type: 'Small Text', label: 'Medium Text', icon: 'FileText' },
			{ type: 'Text', label: 'Long Text', icon: 'AlignLeft' },
		],
	},
	{
		label: 'Numbers',
		types: [
			{ type: 'Int', label: 'Integer', icon: 'Hash' },
			{ type: 'Float', label: 'Decimal', icon: 'Hash' },
			{ type: 'Currency', label: 'Currency', icon: 'DollarSign' },
			{ type: 'Percent', label: 'Percent', icon: 'Percent' },
		],
	},
	{
		label: 'Date & Time',
		types: [
			{ type: 'Date', label: 'Date', icon: 'Calendar' },
			{ type: 'Datetime', label: 'Date & Time', icon: 'CalendarClock' },
			{ type: 'Time', label: 'Time', icon: 'Clock' },
			{ type: 'Duration', label: 'Duration', icon: 'Timer' },
		],
	},
	{
		label: 'Choice',
		types: [
			{ type: 'Select', label: 'Dropdown', icon: 'ChevronDown' },
			{ type: 'Check', label: 'Checkbox', icon: 'CheckSquare' },
			{ type: 'Rating', label: 'Rating', icon: 'Star' },
		],
	},
	{
		label: 'Reference',
		types: [{ type: 'Link', label: 'Link to Table', icon: 'Link2' }],
	},
	{
		label: 'Other',
		types: [
			{ type: 'Color', label: 'Color', icon: 'Palette' },
			{ type: 'Phone', label: 'Phone', icon: 'Phone' },
		],
	},
	{
		label: 'Layout',
		types: [
			{ type: 'Section Break', label: 'Section', icon: 'Minus' },
			{ type: 'Column Break', label: 'Column', icon: 'Columns' },
		],
	},
];

interface FieldTypeSelectorProps {
	onSelect: (type: DataTableFieldType) => void;
	trigger: React.ReactNode;
}

export function FieldTypeSelector({ onSelect, trigger }: FieldTypeSelectorProps) {
	const [open, setOpen] = useState(false);

	const handleSelect = (type: DataTableFieldType) => {
		setOpen(false);
		onSelect(type);
	};

	return (
		<Popover open={open} onOpenChange={setOpen}>
			<PopoverTrigger asChild>{trigger}</PopoverTrigger>
			<PopoverContent className="w-80 p-0" align="center" side="top" collisionPadding={16}>
				<div className="p-3 border-b">
					<h4 className="font-medium text-sm">Choose Field Type</h4>
				</div>
				<div className="p-3 max-h-96 overflow-y-auto space-y-4">
					{GROUPS.map((group) => (
						<div key={group.label}>
							<p className="text-xs font-medium text-muted-foreground mb-2">
								{group.label}
							</p>
							<div className="grid grid-cols-2 gap-1">
								{group.types.map((ft) => {
									const Icon = ICON_MAP[ft.icon] || Type;
									return (
										<Button
											key={ft.type}
											variant="ghost"
											size="sm"
											className="justify-start gap-2 h-8 text-xs font-normal"
											onClick={() => handleSelect(ft.type)}
										>
											<Icon className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
											{ft.label}
										</Button>
									);
								})}
							</div>
						</div>
					))}
				</div>
			</PopoverContent>
		</Popover>
	);
}
