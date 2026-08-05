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
	Folder,
	Minus,
	Columns,
	Paperclip,
	Image,
	LucideIcon,
} from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
	Folder,
	Minus,
	Columns,
	Paperclip,
	Image,
};

interface FieldTypeGroup {
	label: string;
	types: { type: DataTableFieldType; label: string; icon: string }[];
}

const GROUPS: FieldTypeGroup[] = [
	{
		label: 'Text',
		types: [
			{ type: 'Data', label: 'Short text', icon: 'Type' },
			{ type: 'Small Text', label: 'Medium text', icon: 'FileText' },
			{ type: 'Text', label: 'Long text', icon: 'AlignLeft' },
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
		label: 'Date & time',
		types: [
			{ type: 'Date', label: 'Date', icon: 'Calendar' },
			{ type: 'Datetime', label: 'Date & time', icon: 'CalendarClock' },
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
		label: 'Media',
		types: [
			{ type: 'Attach', label: 'File', icon: 'Paperclip' },
			{ type: 'Attach Image', label: 'Image', icon: 'Image' },
		],
	},
	{
		label: 'Layout',
		types: [
			{ type: 'Tab Break', label: 'Tab', icon: 'Folder' },
			{ type: 'Section Break', label: 'Section', icon: 'Minus' },
			{ type: 'Column Break', label: 'Column', icon: 'Columns' },
		],
	},
];

interface FieldTypeSelectorProps {
	onSelect: (type: DataTableFieldType) => void;
	trigger: React.ReactNode;
	value?: DataTableFieldType;
}

export function FieldTypeSelector({ onSelect, trigger, value }: FieldTypeSelectorProps) {
	const [open, setOpen] = useState(false);
	const [query, setQuery] = useState('');

	const handleSelect = (type: DataTableFieldType) => {
		setOpen(false);
		onSelect(type);
	};

	const normalizedQuery = query.trim().toLowerCase();
	const filteredGroups = normalizedQuery
		? GROUPS.map((group) => ({
				...group,
				types: group.types.filter((ft) => ft.label.toLowerCase().includes(normalizedQuery)),
			})).filter((group) => group.types.length > 0)
		: GROUPS;

	return (
		<Popover open={open} onOpenChange={setOpen}>
			<PopoverTrigger asChild>{trigger}</PopoverTrigger>
			<PopoverContent className="w-80 p-0 rounded-lg border border-line bg-panel" align="center" side="top" collisionPadding={16}>
				<div className="sticky top-0 z-10 bg-panel border-b border-line p-3 space-y-2">
					<h4 className="font-medium text-sm">Choose field type</h4>
					<Input
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						placeholder="Search field types"
						className="h-8 text-xs"
					/>
				</div>
				<div className="p-3 max-h-96 overflow-y-auto space-y-4">
					{filteredGroups.map((group) => (
						<div key={group.label}>
							<p className="text-xs font-medium text-steel mb-2">
								{group.label}
							</p>
							<div className="grid grid-cols-2 gap-1">
								{group.types.map((ft) => {
									const Icon = ICON_MAP[ft.icon] || Type;
									const isSelected = ft.type === value;
									return (
										<Button
											key={ft.type}
											variant="ghost"
											size="sm"
											className={`justify-start gap-2 h-[34px] text-xs font-normal rounded ${
												isSelected ? 'border-[1.5px] border-signal bg-signal/[.06]' : ''
											}`}
											onClick={() => handleSelect(ft.type)}
										>
											<Icon className="w-[15px] h-[15px] text-steel shrink-0" />
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
